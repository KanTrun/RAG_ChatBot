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

LOW_VALUE_BLOCK_TYPES = {"acknowledgement", "references", "table_of_contents", "figure_caption", "cover"}


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
    parent_score: float = 0.0
    lexical_signal: float = 0.0
    adjacency_bonus: float = 0.0


def build_summary_subqueries(query: str) -> list[tuple[str, str]]:
    """Return fixed-structure summary probes for NotebookLM-like coverage."""
    return [
        (axis, f"{query}\nFocus: {hint}")
        for axis, _title, hint in SUMMARY_AXIS_CONFIG
    ]


def build_evidence_clusters(
    ranked_chunks: list[RankedChunk],
    *,
    parent_scores: dict[str, float] | None = None,
    target_block_types: tuple[str, ...] = (),
) -> list[EvidenceCluster]:
    """Group reranked chunks into structural evidence clusters."""
    parent_scores = parent_scores or {}
    grouped: dict[str, list[RankedChunk]] = defaultdict(list)
    for chunk in ranked_chunks:
        metadata = chunk.metadata
        cluster_key = (
            str(metadata.get("parent_block_id") or "")
            or str(metadata.get("section_path") or "")
            or str(metadata.get("section") or "")
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
        lexical_signal = max(float(item.metadata.get("lexical_score") or 0.0) for item in items)
        adjacency_bonus = _adjacency_bonus(items)
        parent_score = float(parent_scores.get(cluster_id, 0.0))
        score = max(item.score for item in items)
        score += 0.06 * len(labels)
        score += 0.04 * min(len(items) - 1, 2)
        score += adjacency_bonus
        score += parent_score * 0.12
        score += min(lexical_signal, 1.0) * 0.08
        score += _block_type_bonus(block_type)
        if target_block_types and block_type in target_block_types:
            score += 0.1
        clusters.append(
            EvidenceCluster(
                cluster_id=cluster_id,
                section_path=str(first.metadata.get("section_path") or first.metadata.get("section") or ""),
                block_type=block_type,
                document_id=str(first.metadata.get("document_id") or ""),
                score=score,
                query_labels=labels,
                chunks=items,
                parent_score=parent_score,
                lexical_signal=lexical_signal,
                adjacency_bonus=adjacency_bonus,
            )
        )

    clusters.sort(key=lambda item: item.score, reverse=True)
    return clusters


def select_evidence_chunks(
    intent: str,
    clusters: list[EvidenceCluster],
    *,
    top_k: int,
    target_block_types: tuple[str, ...] = (),
    require_multi_section: bool = False,
) -> tuple[list[RankedChunk], dict]:
    """Select final chunks with section coverage and document diversity."""
    selected: list[RankedChunk] = []
    selected_cluster_ids: set[str] = set()
    used_sections: set[str] = set()
    used_documents: set[str] = set()
    cluster_coverage: list[dict] = []

    if intent == "summary":
        for axis, _title, _hint in SUMMARY_AXIS_CONFIG:
            cluster = next(
                (
                    item
                    for item in clusters
                    if item.cluster_id not in selected_cluster_ids
                    and axis in item.query_labels
                    and item.block_type not in LOW_VALUE_BLOCK_TYPES
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
            cluster_coverage.append(_cluster_diagnostic(cluster))

    if intent in {"factual", "definition"} and target_block_types:
        for cluster in clusters:
            if len(selected) >= top_k:
                break
            if cluster.cluster_id in selected_cluster_ids:
                continue
            if cluster.block_type not in target_block_types:
                continue
            if cluster.block_type in LOW_VALUE_BLOCK_TYPES:
                continue
            selected.append(_annotate_chunk(cluster.chunks[0], None, cluster))
            selected_cluster_ids.add(cluster.cluster_id)
            if cluster.section_path:
                used_sections.add(cluster.section_path)
            cluster_coverage.append(_cluster_diagnostic(cluster))

    for cluster in clusters:
        if len(selected) >= top_k:
            break
        if cluster.cluster_id in selected_cluster_ids:
            continue
        if cluster.block_type in LOW_VALUE_BLOCK_TYPES and len(selected) >= 1:
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
        cluster_coverage.append(_cluster_diagnostic(cluster))

    if require_multi_section and len({chunk.metadata.get("section_path") for chunk in selected}) < 2:
        for cluster in clusters:
            if len(selected) >= top_k:
                break
            if cluster.cluster_id in selected_cluster_ids:
                continue
            if cluster.section_path and cluster.section_path in used_sections:
                continue
            selected.append(_annotate_chunk(cluster.chunks[0], None, cluster))
            selected_cluster_ids.add(cluster.cluster_id)
            if cluster.section_path:
                used_sections.add(cluster.section_path)
            cluster_coverage.append(_cluster_diagnostic(cluster))
            if len({chunk.metadata.get("section_path") for chunk in selected}) >= 2:
                break

    # Second pass: fill remaining top_k slots from unselected non-boilerplate clusters
    if len(selected) < top_k:
        for cluster in clusters:
            if len(selected) >= top_k:
                break
            if cluster.cluster_id in selected_cluster_ids:
                continue
            if cluster.block_type in LOW_VALUE_BLOCK_TYPES:
                continue
            selected.append(_annotate_chunk(cluster.chunks[0], None, cluster))
            selected_cluster_ids.add(cluster.cluster_id)
            if cluster.section_path:
                used_sections.add(cluster.section_path)
            cluster_coverage.append(_cluster_diagnostic(cluster))

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
        "cluster_coverage": cluster_coverage,
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
    metadata["block_type"] = metadata.get("block_type") or cluster.block_type
    metadata["section_path"] = metadata.get("section_path") or cluster.section_path
    metadata["cluster_id"] = cluster.cluster_id
    metadata["selection_reason"] = (
        f"{cluster.block_type.replace('_', ' ')} evidence from {section_label}; "
        f"cluster score={cluster.score:.3f}, adjacency_bonus={cluster.adjacency_bonus:.3f}"
    )
    metadata["cluster_score"] = round(cluster.score, 4)

    return RankedChunk(
        chunk_id=chunk.chunk_id,
        content=chunk.content,
        score=chunk.score,
        original_rank=chunk.original_rank,
        metadata=metadata,
    )


def _adjacency_bonus(items: list[RankedChunk]) -> float:
    if len(items) <= 1:
        return 0.0

    indices = [int(item.metadata.get("chunk_index") or 0) for item in items]
    close_pairs = 0
    for left, right in zip(indices, indices[1:]):
        if right - left <= 2:
            close_pairs += 1
    return min(close_pairs * 0.03, 0.09)


def _cluster_diagnostic(cluster: EvidenceCluster) -> dict:
    return {
        "cluster_id": cluster.cluster_id,
        "section_path": cluster.section_path,
        "block_type": cluster.block_type,
        "score": round(cluster.score, 4),
        "query_labels": sorted(cluster.query_labels),
        "parent_score": round(cluster.parent_score, 4),
    }


def _block_type_bonus(block_type: str) -> float:
    return {
        "problem_statement": 0.12,
        "method": 0.16,
        "results": 0.16,
        "conclusion": 0.12,
        "limitations_scope": 0.1,
        "abstract": 0.1,
        "introduction": 0.08,
        "body": 0.05,
        "procedure": 0.16,
        "requirements": 0.15,
        "legal_clause": 0.14,
        "timeline": 0.1,
        "appendix": -0.08,
        "figure_caption": -0.22,
        "acknowledgement": -0.42,
        "references": -0.52,
        "table_of_contents": -0.6,
        "cover": -0.35,
    }.get(block_type, 0.0)
