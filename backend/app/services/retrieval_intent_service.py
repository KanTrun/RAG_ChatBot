"""Lightweight intent detection and retrieval planning for RAG chat."""

from dataclasses import dataclass
from enum import Enum


class RetrievalIntent(str, Enum):
    question = "question"
    summary = "summary"
    compare = "compare"
    extract = "extract"


@dataclass(frozen=True)
class RetrievalPlan:
    intent: RetrievalIntent
    top_k_search: int
    top_k_rerank: int
    confidence_threshold: float
    context_max_tokens: int
    prefer_document_order: bool = False
    balanced_per_document: bool = False
    ordered_document_scan: bool = False
    summary_axes: tuple[str, ...] = ()


SUMMARY_MARKERS = (
    "summary",
    "summarize",
    "tóm tắt",
    "tom tat",
    "overview",
    "đại ý",
    "noi dung chinh",
    "nội dung chính",
)
COMPARE_MARKERS = (
    "compare",
    "comparison",
    "so sánh",
    "khác nhau",
    "giống nhau",
    "difference",
    "similar",
)
EXTRACT_MARKERS = (
    "quote",
    "trích",
    "trích dẫn",
    "extract",
    "liệt kê",
    "list all",
    "exact",
    "nguyên văn",
)


def detect_retrieval_intent(query: str) -> RetrievalIntent:
    normalized = query.strip().lower()

    if any(marker in normalized for marker in COMPARE_MARKERS):
        return RetrievalIntent.compare
    if any(marker in normalized for marker in SUMMARY_MARKERS):
        return RetrievalIntent.summary
    if any(marker in normalized for marker in EXTRACT_MARKERS):
        return RetrievalIntent.extract
    return RetrievalIntent.question


def build_retrieval_plan(query: str, active_document_count: int) -> RetrievalPlan:
    intent = detect_retrieval_intent(query)

    if intent == RetrievalIntent.summary:
        return RetrievalPlan(
            intent=intent,
            top_k_search=28,
            top_k_rerank=12,
            confidence_threshold=0.18,
            context_max_tokens=4200,
            prefer_document_order=True,
            balanced_per_document=active_document_count > 1,
            ordered_document_scan=False,
            summary_axes=(
                "topic",
                "objective_problem",
                "method",
                "results_contributions",
                "limitations_scope",
            ),
        )

    if intent == RetrievalIntent.compare:
        return RetrievalPlan(
            intent=intent,
            top_k_search=28,
            top_k_rerank=12,
            confidence_threshold=0.28,
            context_max_tokens=4200,
            balanced_per_document=active_document_count > 1,
        )

    if intent == RetrievalIntent.extract:
        return RetrievalPlan(
            intent=intent,
            top_k_search=20,
            top_k_rerank=8,
            confidence_threshold=0.32,
            context_max_tokens=3200,
        )

    return RetrievalPlan(
        intent=RetrievalIntent.question,
        top_k_search=24,
        top_k_rerank=8,
        confidence_threshold=0.35,
        context_max_tokens=3800,
    )
