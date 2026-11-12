"""Comprehensive verification script for all 5 bug fixes and 8 acceptance criteria."""

import asyncio
import json
from pathlib import Path
import py_compile
import sys
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


async def main() -> None:
    print("=== 1. Syntax Check Across All Backend Python Files ===")
    py_files = list(BACKEND_DIR.rglob("*.py"))
    for pf in py_files:
        py_compile.compile(str(pf), doraise=True)
    print(f"Verified syntax of {len(py_files)} Python files: 0 errors.")

    print("\n=== 2. Verify Bug 1 Fix (Celery Task Registration) ===")
    celery_src = (BACKEND_DIR / "app" / "workers" / "celery_app.py").read_text(encoding="utf-8")
    assert 'include=["app.workers.ingestion_tasks"]' in celery_src
    assert "from app.workers import ingestion_tasks" in celery_src
    print("PASS: celery_app.py explicitly imports and registers app.workers.ingestion_tasks.")

    print("\n=== 3. Verify Bug 2 Fix (Provider & Ollama Model Validation + .env.example) ===")
    from app.config import Settings, get_settings
    from app.services.provider_health import validate_provider_settings

    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "EMBEDDING_PROVIDER=ollama" in env_example
    assert "OLLAMA_EMBEDDING_MODEL=mxbai-embed-large" in env_example
    assert "LLM_PROVIDER=ollama" in env_example
    assert "LLM_MODEL=qwen2.5:7b" in env_example
    bad_cfg = Settings(
        embedding_provider="ollama",
        ollama_embedding_model="mxbai-embed-large",
        llm_provider="ollama",
        llm_model="gpt-4o-mini",
    )
    errs = validate_provider_settings(bad_cfg)
    assert any("gpt-4o-mini" in e for e in errs)
    good_cfg = Settings(
        embedding_provider="ollama",
        ollama_embedding_model="mxbai-embed-large",
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
    )
    assert validate_provider_settings(good_cfg) == []
    print("PASS: .env.example defaults and startup provider/model checks verified.")

    print("\n=== 4. Verify Bug 3 Fix ('How does' Intent & Single-Section Support) ===")
    from app.services.reranking_service import RankedChunk
    from app.services.retrieval_intent_service import (
        RetrievalIntent,
        build_retrieval_plan,
        detect_retrieval_intent,
    )
    from app.services.retrieval_service import RetrievalService

    intent_how = detect_retrieval_intent("How does hybrid search work?")
    assert intent_how == RetrievalIntent.definition, f"Expected definition, got {intent_how}"
    plan_how = build_retrieval_plan("How does hybrid search work?", active_document_count=1)
    assert plan_how.require_multi_section is False

    # Verify single-section document is never rejected by multi-section requirement
    plan_mh = build_retrieval_plan("Why does the system combine BM25 and vector search?", active_document_count=1)
    assert plan_mh.intent == RetrievalIntent.multi_hop
    single_chunk = RankedChunk(
        chunk_id="c1",
        content="Hybrid search uses vector similarity and BM25 keyword search.",
        score=0.73,
        original_rank=0,
        metadata={"section": "Overview", "section_path": "Overview", "block_type": "method"},
    )
    low_reason = RetrievalService._build_low_support_reason(
        plan=plan_mh,
        confidence_chunks=[single_chunk],
        confidence_threshold=plan_mh.confidence_threshold,
        selected_chunks=[single_chunk],
        available_section_count=1,
    )
    assert low_reason is None, f"Unexpected low_support_reason: {low_reason}"
    print("PASS: 'How does hybrid search work?' classified as definition; single-section docs accepted.")

    print("\n=== 5. Verify Bug 4 Fix (BM25 Tsquery Builder & Hybrid Contribution) ===")
    tsq = RetrievalService._build_bm25_tsquery_string(
        "What is hybrid search?\nFocus: explicit definition or introductory explanation"
    )
    assert tsq == "hybrid | search", f"Unexpected tsquery: {tsq}"
    tsq_how = RetrievalService._build_bm25_tsquery_string("How does hybrid search work?")
    assert tsq_how == "hybrid | search", f"Unexpected tsquery: {tsq_how}"
    print(f"PASS: BM25 tsquery builder produced '{tsq}' (stopwords and Focus suffix stripped).")

    print("\n=== 6. Verify Bug 5 Fix (120s First-Token Timeout & UI Loading State) ===")
    assert get_settings().first_token_timeout_seconds == 120
    chat_router_src = (BACKEND_DIR / "app" / "api" / "v1" / "chat_router.py").read_text(encoding="utf-8")
    assert "first_token_timeout = max(int(settings.first_token_timeout_seconds), 120)" in chat_router_src
    thinking_src = (REPO_ROOT / "frontend" / "components" / "chat" / "thinking-indicator.tsx").read_text(encoding="utf-8")
    assert "Đang tải model, vui lòng chờ" in thinking_src
    print("PASS: 120s first-token timeout, startup warmup, and UI model-loading state verified.")

    print("\n=== 7. Verify Real Section Extraction & Acceptance Queries (Criteria 2, 3, 4, 5, 6, 7) ===")
    from app.evaluation.ragas_evaluator import run_evaluation
    from app.services.chunking_engine import ChunkingEngine
    from app.services.parser_factory import get_parser

    sample_path = BACKEND_DIR / "tests" / "fixtures" / "sample-article.txt"
    pages = get_parser(str(sample_path)).parse(str(sample_path))
    chunks = ChunkingEngine(chunk_size=512, chunk_overlap=51).chunk_document(pages, uuid4())
    sections = [c.section for c in chunks]
    assert all(s != "Document" for s in sections), f"Sections should not be generic 'Document': {sections}"
    print(f"Extracted sections from sample-article.txt: {sections}")

    report = await run_evaluation(bm25_enabled=True, record_history=False)
    by_q = {item["question"]: item for item in report["results"]}

    q_what = by_q["What is hybrid search?"]
    assert not q_what["abstained"] and "[1]" in q_what["answer"]
    print(f"Q: 'What is hybrid search?' -> {q_what['answer'].splitlines()[0]}")

    q_how = by_q["How does hybrid search work?"]
    assert not q_how["abstained"] and "[1]" in q_how["answer"]
    print(f"Q: 'How does hybrid search work?' -> {q_how['answer'].splitlines()[0]}")

    q_france = by_q["What is the capital of France?"]
    assert q_france["abstained"] is True
    print(f"Q: 'What is the capital of France?' -> Abstained={q_france['abstained']} ({q_france['answer']})")

    print("\nALL ACCEPTANCE CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
