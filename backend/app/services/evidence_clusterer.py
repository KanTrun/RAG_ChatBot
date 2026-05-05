"""Runtime evidence clustering and selection for retrieval."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.services.reranking_service import RankedChunk

SUMMARY_AXIS_CONFIG: tuple[tuple[str, str, str], ...] = (
    ("topic", "Chu de/de tai", "chu de de tai topic title overview"),
    ("objective_problem", "Muc tieu/bai toan", "muc tieu bai toan objective problem statement"),
    ("method", "Phuong phap chinh", "phuong phap methodology approach"),
    ("results_contributions", "Ket qua/dong gop", "ket qua dong gop results contributions evaluation"),
    ("limitations_scope", "Gioi han/pham vi", "gioi han pham vi limitations scope constraints"),
)


@dataclass
class EvidenceCluster:
    """A group of adjacent chunks from the same structural parent."""

    cluster_id: str
    section_path: str
    block_type: str
    document_id: str
    score: float
    query_labels: set[str]
    chunks: list[RankedChunk]


def build_summary_subqueries(query: str) -> list[tuple[str, str]]:
    """Return fixed-structure summary probes for NotebookLM-like coverage."""
    return [
        (axis, f"{query}\nFocus: {hint}")
        for axis, _title, hint in SUMMARY_AXIS_CONFIG
    ]


def build_evidence_clusters(ranked_chunks: list[RankedChunk]) -> list[EvidenceCluster]:
    """Group reranked chunks into structural evidence clusters."""
    grouped: dict[str, list[RankedChunk]] = defaultdict(list)
    for chunk in ranked_chunks:
        metadata = chunk.metadata
        cluster_key = (
            str(metadata.get("parent_block_id"))
            or str(metadata.get("section_path"))
            or str(metadata.get("section"))
            or chunk.chunk_id
        )
        grouped[cluster_key].append(chunk)

    clusters: list[EvidenceCluster] = []
    for cluster_id, items in grouped.items():
        items.sort(
            key=lambda item: (
                item.metadata.get("page_start") or item.metadata.get("page_number") or 0,
                item.metadata.get("chunk_index") or 0,
                item.original_rank,
            )
        )
        first = items[0]
        labels = {
            label
            for item in items
            for label in item.metadata.get("query_labels", [])
            if label not in {"primary", "rewrite"}
        }
        block_type = str(first.metadata.get("block_type") or "body")
        score = max(item.score for item in items)
        score += 0.06 * len(labels)
        score += 0.03 * min(len(items) - 1, 2)
        score += _block_type_bonus(block_type)
        clusters.append(
            EvidenceCluster(
                cluster_id=cluster_id,
                section_path=str(first.metadata.get("section_path") or first.metadata.get("section") or ""),
                block_type=block_type,
                document_id=str(first.metadata.get("document_id") or ""),
                score=score,
                query_labels=labels,
                chunks=items,
            )
        )

    clusters.sort(key=lambda item: item.score, reverse=True)
    return clusters


def select_evidence_chunks(
    intent: str,
    clusters: list[EvidenceCluster],
    *,
    top_k: int,
) -> tuple[list[RankedChunk], dict]:
    """Select final chunks with section coverage and document diversity."""
    selected: list[RankedChunk] = []
    selected_cluster_ids: set[str] = set()
    used_sections: set[str] = set()
    used_documents: set[str] = set()

    if intent == "summary":
        for axis, _title, _hint in SUMMARY_AXIS_CONFIG:
            cluster = next(
                (
                    item
                    for item in clusters
                    if item.cluster_id not in selected_cluster_ids
                    and axis in item.query_labels
                    and item.block_type not in {"acknowledgement", "references", "table_of_contents", "figure_caption", "cover"}
                ),
                None,
            )
            if cluster is None:
                continue
            selected.append(_annotate_chunk(cluster.chunks[0], axis, cluster))
            selected_cluster_ids.add(cluster.cluster_id)
            used_sections.add(cluster.section_path)
            if cluster.document_id:
                used_documents.add(cluster.document_id)

    for cluster in clusters:
        if len(selected) >= top_k:
            break
        if cluster.cluster_id in selected_cluster_ids:
            continue
        if intent == "compare" and cluster.document_id and cluster.document_id in used_documents:
            continue
        if cluster.section_path and cluster.section_path in used_sections and len(selected) >= max(2, top_k // 2):
            continue

        selected.append(_annotate_chunk(cluster.chunks[0], None, cluster))
        selected_cluster_ids.add(cluster.cluster_id)
        if cluster.section_path:
            used_sections.add(cluster.section_path)
        if cluster.document_id:
            used_documents.add(cluster.document_id)

    if len(selected) < top_k:
        for cluster in clusters:
            if len(selected) >= top_k:
                break
            for chunk in cluster.chunks[1:]:
                selected.append(_annotate_chunk(chunk, None, cluster))
                if len(selected) >= top_k:
                    break

    diagnostics = {
        "selected_sections": [chunk.metadata.get("section_path") for chunk in selected if chunk.metadata.get("section_path")],
        "selected_block_types": [chunk.metadata.get("block_type") for chunk in selected],
        "summary_axes_covered": sorted(
            {
                axis
                for chunk in selected
                for axis in chunk.metadata.get("coverage_labels", [])
                if axis not in {"primary", "rewrite"}
            }
        ),
    }
    return selected[:top_k], diagnostics


def _annotate_chunk(
    chunk: RankedChunk,
    answer_section: str | None,
    cluster: EvidenceCluster,
) -> RankedChunk:
    metadata = dict(chunk.metadata)
    coverage_labels = set(metadata.get("query_labels", []))
    if answer_section:
        coverage_labels.add(answer_section)

    section_label = cluster.section_path or str(metadata.get("section") or "document body")
    metadata["coverage_labels"] = sorted(coverage_labels)
    metadata["answer_section"] = answer_section
    metadata["selection_reason"] = f"{cluster.block_type.replace('_', ' ')} evidence from {section_label}"
    metadata["cluster_score"] = round(cluster.score, 4)

    return RankedChunk(
        chunk_id=chunk.chunk_id,
        content=chunk.content,
        score=chunk.score,
        original_rank=chunk.original_rank,
        metadata=metadata,
    )


def _block_type_bonus(block_type: str) -> float:
    return {
        "problem_statement": 0.12,
        "method": 0.14,
        "results": 0.14,
        "conclusion": 0.12,
        "limitations_scope": 0.1,
        "abstract": 0.08,
        "introduction": 0.06,
        "body": 0.05,
        "appendix": -0.08,
        "figure_caption": -0.2,
        "acknowledgement": -0.42,
        "references": -0.52,
        "table_of_contents": -0.6,
        "cover": -0.35,
    }.get(block_type, 0.0)
