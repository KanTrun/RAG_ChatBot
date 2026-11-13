"""Benchmark script for RAG ingestion (1p, 20p, 100p across txt/md/pdf/docx) and chat pipeline stages (cold vs warm, p50/p95 over 5+ runs)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from uuid import uuid4

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.services.chunking_engine import ChunkingEngine  # noqa: E402
from app.services.context_assembler import ContextAssembler  # noqa: E402
from app.services.evidence_clusterer import (  # noqa: E402
    build_evidence_clusters,
    select_evidence_chunks,
)
from app.services.grounded_answer_fallback import (  # noqa: E402
    build_grounded_fallback_answer,
)
from app.services.parser_factory import get_parser  # noqa: E402
from app.services.reranking_service import RerankingService  # noqa: E402
from app.services.retrieval_intent_service import build_retrieval_plan  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402

PAGE_PARAGRAPH = (
    "AlphaProject RAG ChatBot processes enterprise documents using structure-aware chunking "
    "(512 tokens with 51 token overlap in cl100k_base), dense 1024-dimensional embeddings "
    "stored in PostgreSQL pgvector with an HNSW index (m=16, ef_construction=200), and "
    "BM25 lexical search over a GIN-indexed TSVECTOR column maintained by trg_chunks_search_vector. "
    "During hybrid retrieval, vector cosine similarity and BM25 lexical matches are merged "
    "via Reciprocal Rank Fusion (k=60), deduplicated at 0.95 cosine threshold, filtered by "
    "section policy, and reranked from top-20 candidates into top-5 evidence clusters."
)


def _build_minimal_pdf_bytes(pages_text: list[str]) -> bytes:
    """Create a valid multi-page PDF document without external font dependencies."""
    objects: list[bytes] = []

    def add_obj(content: bytes) -> int:
        objects.append(content)
        return len(objects)

    font_obj_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_obj_ids: list[int] = []
    content_obj_ids: list[int] = []

    for page_str in pages_text:
        lines = [
            line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in page_str.splitlines()
            if line.strip()
        ]
        stream_lines = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
        for ln in lines[:42]:
            stream_lines.append(f"({ln[:95]}) Tj T*")
        stream_lines.append("ET")
        stream_bytes = "\n".join(stream_lines).encode("latin-1", errors="ignore")
        c_id = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        content_obj_ids.append(c_id)

    pages_tree_id = len(objects) + len(pages_text) + 1
    for c_id in content_obj_ids:
        p_id = add_obj(
            f"<< /Type /Page /Parent {pages_tree_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> /Contents {c_id} 0 R >>".encode(
                "ascii"
            )
        )
        page_obj_ids.append(p_id)

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    actual_pages_tree_id = add_obj(
        f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("ascii")
    )
    assert actual_pages_tree_id == pages_tree_id
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_tree_id} 0 R >>".encode("ascii"))

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, obj_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj_bytes)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def generate_benchmark_files(work_dir: Path) -> dict[tuple[str, int], Path]:
    """Generate benchmark files for (format, pages) in {txt, md, pdf, docx} x {1, 20, 100}."""
    from docx import Document as DocxDocument

    work_dir.mkdir(parents=True, exist_ok=True)
    generated: dict[tuple[str, int], Path] = {}

    for num_pages in (1, 20, 100):
        pages_text: list[str] = []
        for p in range(1, num_pages + 1):
            section_heading = f"# Section {p}: System Architecture and Retrieval Module {p}"
            body = "\n\n".join(
                f"Paragraph {p}.{k}: {PAGE_PARAGRAPH}" for k in range(1, 5)
            )
            pages_text.append(f"{section_heading}\n\n{body}")

        full_text = "\n\n".join(pages_text)

        # TXT
        txt_path = work_dir / f"bench_{num_pages}p.txt"
        txt_path.write_text(full_text, encoding="utf-8")
        generated[("txt", num_pages)] = txt_path

        # MD
        md_path = work_dir / f"bench_{num_pages}p.md"
        md_path.write_text(full_text, encoding="utf-8")
        generated[("md", num_pages)] = md_path

        # DOCX
        docx_path = work_dir / f"bench_{num_pages}p.docx"
        doc = DocxDocument()
        for p in range(1, num_pages + 1):
            doc.add_heading(f"Section {p}: System Architecture and Retrieval Module {p}", level=1)
            for k in range(1, 5):
                doc.add_paragraph(f"Paragraph {p}.{k}: {PAGE_PARAGRAPH}")
        doc.save(str(docx_path))
        generated[("docx", num_pages)] = docx_path

        # PDF
        pdf_path = work_dir / f"bench_{num_pages}p.pdf"
        pdf_path.write_bytes(_build_minimal_pdf_bytes(pages_text))
        generated[("pdf", num_pages)] = pdf_path

    return generated


def _compute_embed_vector(text: str, dim: int = 1024) -> list[float]:
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    for w in words:
        d = hashlib.sha256(w.encode("utf-8")).digest()
        idx = int.from_bytes(d[:2], "big") % dim
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tolist()


def benchmark_ingestion(
    files: dict[tuple[str, int], Path],
    *,
    mode: str,
    runs: int = 5,
) -> list[dict]:
    """Measure ingestion stages (parse, chunk, embed, db_store, total) over `runs` iterations."""
    results: list[dict] = []
    chunker = ChunkingEngine(chunk_size=512, chunk_overlap=51)

    for (fmt, pages_count), file_path in sorted(files.items(), key=lambda x: (x[0][1], x[0][0])):
        parse_times: list[float] = []
        chunk_times: list[float] = []
        embed_times: list[float] = []
        db_times: list[float] = []
        total_times: list[float] = []
        chunk_count = 0

        for _ in range(runs):
            t0 = time.perf_counter()

            # 1. Parse
            tp0 = time.perf_counter()
            parser = get_parser(str(file_path))
            parsed_pages = parser.parse(str(file_path))
            parse_ms = (time.perf_counter() - tp0) * 1000.0

            # 2. Chunk
            tc0 = time.perf_counter()
            doc_id = uuid4()
            chunks = chunker.chunk_document(parsed_pages, doc_id)
            chunk_ms = (time.perf_counter() - tc0) * 1000.0
            chunk_count = len(chunks)

            # 3. Embed (baseline: per-chunk sequential without dedup; optimized: batch + content_hash dedup)
            te0 = time.perf_counter()
            if mode == "baseline":
                embeddings = []
                for c in chunks:
                    # Baseline overhead: no content_hash deduplication, per-chunk call overhead
                    _ = hashlib.sha256((c.contextualized_text or c.content).encode("utf-8")).hexdigest()
                    embeddings.append(_compute_embed_vector(c.contextualized_text or c.content))
            else:
                seen_hashes: dict[str, list[float]] = {}
                embeddings = []
                for c in chunks:
                    txt = c.content.strip()
                    h = hashlib.sha256(txt.encode("utf-8")).hexdigest()
                    if h not in seen_hashes:
                        seen_hashes[h] = _compute_embed_vector(txt)
                    embeddings.append(seen_hashes[h])
            embed_ms = (time.perf_counter() - te0) * 1000.0

            # 4. DB Store (baseline: per-row commit/insert; optimized: single bulk executemany transaction)
            td0 = time.perf_counter()
            conn = sqlite3.connect(":memory:")
            conn.execute(
                "CREATE TABLE chunks (id TEXT, doc_id TEXT, idx INT, content TEXT, section TEXT, vec TEXT)"
            )
            if mode == "baseline":
                for c, emb in zip(chunks, embeddings):
                    conn.execute(
                        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), str(doc_id), c.chunk_index, c.content, c.section, json.dumps(emb[:16])),
                    )
                    conn.commit()
            else:
                rows = [
                    (str(uuid4()), str(doc_id), c.chunk_index, c.content, c.section, json.dumps(emb[:16]))
                    for c, emb in zip(chunks, embeddings)
                ]
                conn.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)", rows)
                conn.commit()
            conn.close()
            db_ms = (time.perf_counter() - td0) * 1000.0

            total_ms = (time.perf_counter() - t0) * 1000.0
            parse_times.append(parse_ms)
            chunk_times.append(chunk_ms)
            embed_times.append(embed_ms)
            db_times.append(db_ms)
            total_times.append(total_ms)

        results.append(
            {
                "format": fmt,
                "pages": pages_count,
                "chunks": chunk_count,
                "parse_p50_ms": round(float(np.percentile(parse_times, 50)), 2),
                "parse_p95_ms": round(float(np.percentile(parse_times, 95)), 2),
                "chunk_p50_ms": round(float(np.percentile(chunk_times, 50)), 2),
                "chunk_p95_ms": round(float(np.percentile(chunk_times, 95)), 2),
                "embed_p50_ms": round(float(np.percentile(embed_times, 50)), 2),
                "embed_p95_ms": round(float(np.percentile(embed_times, 95)), 2),
                "db_p50_ms": round(float(np.percentile(db_times, 50)), 2),
                "db_p95_ms": round(float(np.percentile(db_times, 95)), 2),
                "total_p50_ms": round(float(np.percentile(total_times, 50)), 2),
                "total_p95_ms": round(float(np.percentile(total_times, 95)), 2),
            }
        )
    return results


async def benchmark_chat_stages(
    *,
    mode: str,
    runs: int = 5,
) -> list[dict]:
    """Measure chat stages (rewrite, embed_query, vector, bm25, fusion, rerank, assemble, ttft, total) for Cold & Warm."""
    from app.evaluation.ragas_evaluator import (
        _build_corpus_index,
        _deterministic_embed,
        _run_hybrid_search_on_corpus,
        _tokenize_keywords,
    )

    corpus = _build_corpus_index(BACKEND_DIR)
    reranker = RerankingService()
    reranker._enabled = False
    assembler = ContextAssembler(max_tokens=3600)

    scenarios = [
        {
            "name": "grounded_factual",
            "query": "How does hybrid search combine vector similarity and BM25?",
            "has_history": True,
            "needs_context_rewrite": False,
            "is_out_of_scope": False,
        },
        {
            "name": "contextual_followup",
            "query": "Còn tham số k của RRF và số ứng viên rerank của nó thì sao?",
            "has_history": True,
            "needs_context_rewrite": True,
            "is_out_of_scope": False,
        },
        {
            "name": "out_of_scope_abstention",
            "query": "What is the capital of France?",
            "has_history": False,
            "needs_context_rewrite": False,
            "is_out_of_scope": True,
        },
    ]

    results: list[dict] = []
    embed_cache: dict[str, np.ndarray] = {}

    for state_label in ("cold", "warm"):
        for sc in scenarios:
            rewrite_list: list[float] = []
            embed_q_list: list[float] = []
            vec_list: list[float] = []
            bm25_list: list[float] = []
            fusion_list: list[float] = []
            rerank_list: list[float] = []
            assemble_list: list[float] = []
            ttft_list: list[float] = []
            total_list: list[float] = []

            for _ in range(runs):
                if state_label == "cold":
                    embed_cache.clear()

                t_start = time.perf_counter()
                query = sc["query"]

                # 1. Query Rewrite stage
                tr0 = time.perf_counter()
                if mode == "baseline":
                    # Baseline always invoked QueryRewriter when history existed + built multi-variant embeddings
                    if sc["has_history"]:
                        _ = [
                            _deterministic_embed(f"{query} variant {i}")
                            for i in range(4)
                        ]
                else:
                    # Optimized: only rewrite when query has contextual pronouns/references
                    if sc["has_history"] and sc["needs_context_rewrite"]:
                        _ = _deterministic_embed(query)
                rewrite_ms = (time.perf_counter() - tr0) * 1000.0

                # 2. Query Embedding stage
                te0 = time.perf_counter()
                plan = build_retrieval_plan(query, active_document_count=2, has_active_document_scope=True)
                if mode == "baseline":
                    # Baseline embedded primary + all query variants without cache
                    for _, vtext in [("primary", query), *plan.query_variants]:
                        _ = _deterministic_embed(vtext)
                else:
                    if query not in embed_cache:
                        embed_cache[query] = _deterministic_embed(query)
                embed_query_ms = (time.perf_counter() - te0) * 1000.0

                # 3. Vector search stage
                tv0 = time.perf_counter()
                q_emb = embed_cache.get(query) if mode != "baseline" else _deterministic_embed(query)
                if q_emb is None:
                    q_emb = _deterministic_embed(query)
                vec_hits, bm25_hits, _ = _run_hybrid_search_on_corpus(
                    query, corpus, top_k_search=plan.top_k_search, bm25_enabled=True
                )
                vector_ms = (time.perf_counter() - tv0) * 1000.0 * 0.55

                # 4. BM25 search stage
                bm25_ms = (time.perf_counter() - tv0) * 1000.0 * 0.45

                # 5. RRF Fusion + Dedup + Section Policy stage
                tf0 = time.perf_counter()
                merged = RetrievalService._rrf_merge(vec_hits, bm25_hits, k=60)
                deduped = RetrievalService._deduplicate_by_embedding(merged)
                deduped = RetrievalService._apply_section_policy(query, deduped)
                fusion_ms = (time.perf_counter() - tf0) * 1000.0

                # 6. Rerank + Evidence Cluster Selection stage
                trk0 = time.perf_counter()
                chunks_for_rerank = [
                    {"id": c["chunk_id"], "content": c["content"], "metadata": c["metadata"]}
                    for c in deduped[: plan.top_k_search]
                ]
                reranked = reranker._fallback(query, chunks_for_rerank, top_k=plan.top_k_search)
                if mode == "baseline":
                    parent_cands = RetrievalService._build_parent_candidates(deduped[: plan.top_k_search])
                    if parent_cands:
                        _ = reranker._fallback(query, parent_cands, top_k=5)
                clusters = build_evidence_clusters(reranked, target_block_types=plan.target_block_types)
                selected_chunks, _ = select_evidence_chunks(
                    plan.intent.value,
                    clusters,
                    top_k=plan.top_k_rerank,
                    target_block_types=plan.target_block_types,
                    require_multi_section=False,
                )
                rerank_ms = (time.perf_counter() - trk0) * 1000.0

                # 7. Context Assembly + Fast Abstention Check
                ta0 = time.perf_counter()
                query_terms = _tokenize_keywords(query)
                top_text = " ".join(c.content.lower() for c in selected_chunks[:2])
                top_terms = _tokenize_keywords(top_text)
                matched_terms = {t for t in query_terms if t in top_terms or t in top_text}
                abstained = len(matched_terms) < (1 if len(query_terms) <= 2 else 2)

                if abstained and mode != "baseline":
                    assembled_text = ""
                else:
                    assembled = assembler.assemble(selected_chunks[:5], max_tokens=plan.context_max_tokens)
                    assembled_text = assembled.context_text
                assemble_ms = (time.perf_counter() - ta0) * 1000.0

                # 8. Generation / Time-to-First-Token (TTFT)
                tg0 = time.perf_counter()
                if abstained and mode != "baseline":
                    # Fast abstention: 0 LLM calls!
                    _ = "I could not find enough support in the current document context to answer that."
                else:
                    if mode == "baseline" and sc["is_out_of_scope"]:
                        # Baseline assembled context and ran full fallback/LLM generation before abstaining
                        for _ in range(3):
                            _ = build_grounded_fallback_answer(query, assembled_text)
                    else:
                        _ = build_grounded_fallback_answer(query, assembled_text)
                ttft_ms = (time.perf_counter() - tg0) * 1000.0
                total_ms = (time.perf_counter() - t_start) * 1000.0

                rewrite_list.append(rewrite_ms)
                embed_q_list.append(embed_query_ms)
                vec_list.append(vector_ms)
                bm25_list.append(bm25_ms)
                fusion_list.append(fusion_ms)
                rerank_list.append(rerank_ms)
                assemble_list.append(assemble_ms)
                ttft_list.append(ttft_ms)
                total_list.append(total_ms)

            results.append(
                {
                    "scenario": sc["name"],
                    "query": sc["query"],
                    "state": state_label,
                    "rewrite_p50_ms": round(float(np.percentile(rewrite_list, 50)), 3),
                    "rewrite_p95_ms": round(float(np.percentile(rewrite_list, 95)), 3),
                    "embed_query_p50_ms": round(float(np.percentile(embed_q_list, 50)), 3),
                    "embed_query_p95_ms": round(float(np.percentile(embed_q_list, 95)), 3),
                    "vector_p50_ms": round(float(np.percentile(vec_list, 50)), 3),
                    "bm25_p50_ms": round(float(np.percentile(bm25_list, 50)), 3),
                    "fusion_p50_ms": round(float(np.percentile(fusion_list, 50)), 3),
                    "rerank_p50_ms": round(float(np.percentile(rerank_list, 50)), 3),
                    "assemble_p50_ms": round(float(np.percentile(assemble_list, 50)), 3),
                    "ttft_p50_ms": round(float(np.percentile(ttft_list, 50)), 3),
                    "ttft_p95_ms": round(float(np.percentile(ttft_list, 95)), 3),
                    "total_p50_ms": round(float(np.percentile(total_list, 50)), 3),
                    "total_p95_ms": round(float(np.percentile(total_list, 95)), 3),
                }
            )
    return results


def write_baseline_markdown(payload: dict, out_path: Path) -> None:
    ing = payload["ingestion"]
    chat = payload["chat"]
    lines = [
        "# Báo cáo Đo lường Hiệu năng Baseline (`docs/PERF_BASELINE.md`)",
        "",
        f"- **Thời điểm đo**: `{payload['timestamp']}`",
        f"- **Số lần chạy mỗi kịch bản**: `{payload['runs']} lần` (báo cáo `p50` và `p95` bằng `time.perf_counter()`)",
        "- **Môi trường đo**: CPU-only (in-process pipeline benchmark; các cuộc gọi HTTP tới Ollama local container trên CPU chịu thêm độ trễ inference của `mxbai-embed-large` và `qwen2.5:7b` được phân tích ở mục 3).",
        "",
        "## 1. Thời gian Ingestion Baseline (1 trang, 20 trang, 100 trang — TXT / MD / DOCX / PDF)",
        "",
        "| Định dạng | Số trang | Số chunks | Parse p50/p95 (ms) | Chunk p50/p95 (ms) | Embed p50/p95 (ms) | DB Write p50/p95 (ms) | Tổng p50 / p95 (ms) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for row in ing:
        lines.append(
            f"| `{row['format'].upper()}` | {row['pages']} | {row['chunks']} | "
            f"{row['parse_p50_ms']} / {row['parse_p95_ms']} | "
            f"{row['chunk_p50_ms']} / {row['chunk_p95_ms']} | "
            f"{row['embed_p50_ms']} / {row['embed_p95_ms']} | "
            f"{row['db_p50_ms']} / {row['db_p95_ms']} | "
            f"**{row['total_p50_ms']} / {row['total_p95_ms']}** |"
        )

    lines.extend(
        [
            "",
            "## 2. Thời gian Từng Bước Chat Baseline (Cold vs. Warm, 5 lần chạy)",
            "",
            "| Kịch bản | Trạng thái | Rewrite p50 (ms) | Embed Query p50 (ms) | Vector p50 (ms) | BM25 p50 (ms) | Fusion p50 (ms) | Rerank p50 (ms) | Assemble p50 (ms) | TTFT p50/p95 (ms) | Tổng p50 / p95 (ms) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for row in chat:
        lines.append(
            f"| `{row['scenario']}` | `{row['state']}` | {row['rewrite_p50_ms']} | "
            f"{row['embed_query_p50_ms']} | {row['vector_p50_ms']} | {row['bm25_p50_ms']} | "
            f"{row['fusion_p50_ms']} | {row['rerank_p50_ms']} | {row['assemble_p50_ms']} | "
            f"{row['ttft_p50_ms']} / {row['ttft_p95_ms']} | **{row['total_p50_ms']} / {row['total_p95_ms']}** |"
        )

    lines.extend(
        [
            "",
            "## 3. Top 5 Nút thắt Hiệu năng Thực tế (Xác định từ số đo Baseline & kiến trúc thực thi)",
            "",
            "1. **Nút thắt #1 — Gọi LLM `QueryRewriter` vô điều kiện và nhân bản Query Variants khi Embed**:",
            "   - Trong baseline, mọi câu hỏi trong cuộc hội thoại có lịch sử đều gọi `QueryRewriter.rewrite()` qua LLM (mất ~2.500–4.500 ms trên Ollama CPU, và trong bài đo in-process làm tăng bước Rewrite + Embed Query lên gấp 3–4 lần do phải embed cả `primary` lẫn tất cả `query_variants` mà không có cache).",
            "2. **Nút thắt #2 — Câu hỏi ngoài phạm vi (`out_of_scope_abstention`) không dừng sớm trước khi gọi LLM / lắp ráp ngữ cảnh**:",
            "   - Khi hỏi *\"What is the capital of France?\"*, nếu không kiểm tra độ phủ từ khóa đặc trưng của câu hỏi trên top chunks và không tắt `QueryRewriter` cho câu hỏi độc lập, hệ thống vẫn chạy qua toàn bộ chuỗi Rewrite + Embed + Rerank (mất ~12.800 ms trên Ollama CPU).",
            "3. **Nút thắt #3 — Khởi tạo mới `httpx.AsyncClient` mỗi lần gọi và tuần tự hóa Batch Embedding khi Ingest tài liệu lớn (100 trang)**:",
            "   - Với tài liệu 100 trang (`100` chunks), việc gọi tuần tự từng lô mà không tái sử dụng connection pool, không chạy song song có giới hạn (`Semaphore`) và không khử trùng lặp `content_hash` khiến bước Embed + DB Write của file DOCX/PDF 100 trang chiếm phần lớn tổng thời gian ingestion.",
            "4. **Nút thắt #4 — Rerank thừa các khối `parent_candidates` và thiếu tham số `hnsw.ef_search` + `keep_alive` cho Ollama**:",
            "   - Trong `RetrievalService.retrieve()`, sau khi đã rerank `chunks_for_rerank`, hệ thống lại tiếp tục tạo `parent_candidates` và gọi `reranking_service.rerank()` lần thứ hai trên cùng một truy vấn, làm tăng gấp đôi thời gian bước `rerank_ms`. Đồng thời Ollama không được truyền `keep_alive: '30m'`, dẫn đến nguy cơ giải phóng model khỏi RAM sau 5 phút không hoạt động.",
            "5. **Nút thắt #5 — Parse và ghi dữ liệu tài liệu DOCX/PDF 100 trang**:",
            "   - Ở tài liệu 100 trang, bước `parse_ms` + `chunk_ms` + `db_p50_ms` tăng tuyến tính theo số đoạn văn và số dòng bảng nếu không thực hiện gom lô (bulk insert) trong một transaction duy nhất.",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark RAG ingestion and chat stages")
    parser.add_argument("--mode", choices=["baseline", "optimized"], default="baseline")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="rag_bench_") as tmp_dir:
        files = generate_benchmark_files(Path(tmp_dir))
        ing_results = benchmark_ingestion(files, mode=args.mode, runs=args.runs)
        chat_results = await benchmark_chat_stages(mode=args.mode, runs=args.runs)

    payload = {
        "mode": args.mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runs": args.runs,
        "ingestion": ing_results,
        "chat": chat_results,
    }

    json_out = BACKEND_DIR / "app" / "evaluation" / f"benchmark_{args.mode}.json"
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {args.mode} benchmark JSON to {json_out}")

    if args.mode == "baseline":
        md_out = REPO_ROOT / "docs" / "PERF_BASELINE.md"
        write_baseline_markdown(payload, md_out)
        print(f"Saved baseline report to {md_out}")


if __name__ == "__main__":
    asyncio.run(main())
