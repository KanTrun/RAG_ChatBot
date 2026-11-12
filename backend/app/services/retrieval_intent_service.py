"""Intent detection and retrieval planning for document-first RAG chat."""

from dataclasses import dataclass
from enum import Enum


class RetrievalIntent(str, Enum):
    question = "question"
    summary = "summary"
    compare = "compare"
    extract = "extract"
    factual = "factual"
    definition = "definition"
    multi_hop = "multi_hop"


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
    target_block_types: tuple[str, ...] = ()
    query_variants: tuple[tuple[str, str], ...] = ()
    require_multi_section: bool = False
    low_support_hint: str = "The retrieved evidence does not support the answer strongly enough."
    query_classification: str = "general-allowed"
    document_target_required: bool = False
    classification_reason: str = "The query looks like a general question."
    outside_knowledge_blocked_reason: str | None = None
    exhaustive_mode: bool = False
    coverage_min_sections: int = 1


SUMMARY_MARKERS = (
    "summary",
    "summarize",
    "tóm tắt",
    "tom tat",
    "overview",
    "đại ý",
    "noi dung chinh",
    "nội dung chính",
    "ý chính",
    "main idea",
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
DEFINITION_MARKERS = (
    "what is",
    "how does",
    "how do",
    "define",
    "definition",
    "là gì",
    "la gi",
    "hoạt động như thế nào",
    "hoat dong nhu the nao",
    "định nghĩa",
    "dinh nghia",
    "meaning of",
)
FACTUAL_MARKERS = (
    "which",
    "what model",
    "what algorithm",
    "what method",
    "what approach",
    "used",
    "use",
    "sử dụng",
    "su dung",
    "gồm",
    "bao gồm",
    "tên",
    "name",
)
MULTI_HOP_MARKERS = (
    "why",
    "tại sao",
    "tai sao",
    "relationship",
    "liên hệ",
    "tong hop",
    "tổng hợp",
    "combine",
    "combined",
    "affect",
    "impact",
    "influence",
    "relate to",
)

SUMMARY_AXES = (
    "topic",
    "objective_problem",
    "method",
    "results_contributions",
    "limitations_scope",
)
DOCUMENT_REFERENCE_MARKERS = (
    "this document",
    "this file",
    "this paper",
    "this guide",
    "this manual",
    "this report",
    "this tutorial",
    "this cv",
    "this resume",
    "current document",
    "current file",
    "these guides",
    "these manuals",
    "these reports",
    "uploaded document",
    "uploaded file",
    "according to the document",
    "based on the document",
    "in the document",
    "tai lieu nay",
    "file nay",
    "cv nay",
    "ho so nay",
    "trong tai lieu",
    "dua tren tai lieu",
)
CV_REFERENCE_MARKERS = (
    "cv",
    "resume",
    "ho so",
    "profile",
    "curriculum vitae",
)
EXHAUSTIVE_MARKERS = (
    "all",
    "all of",
    "all information",
    "everything",
    "every",
    "entire",
    "full list",
    "complete list",
    "full content",
    "toan bo",
    "toan bo noi dung",
    "tat ca",
    "liet ke het",
    "liet ke toan bo",
    "day du",
    "all sections",
    "all mentions",
)
DOCUMENT_CONTENT_MARKERS = (
    "summary",
    "summarize",
    "main idea",
    "content",
    "topic",
    "objective",
    "problem",
    "scope",
    "method",
    "approach",
    "result",
    "conclusion",
    "contribution",
    "finding",
    "skill",
    "experience",
    "project",
    "education",
    "responsibilit",
    "technology",
    "stack",
    "tom tat",
    "noi dung",
    "y chinh",
    "muc tieu",
    "bai toan",
    "phuong phap",
    "ket qua",
    "ket luan",
    "dong gop",
    "ky nang",
    "kinh nghiem",
    "hoc van",
    "section",
    "page",
    "mention",
    "listed",
    "described",
    "stated",
    "contains",
    "include",
    "author",
    "email",
    "phone",
    "timeline",
    "date",
    "deadline",
    "step",
    "procedure",
    "instruction",
    "requirement",
    "clause",
    "contract",
    "policy",
    "manual",
    "report",
    "slide",
)
GENERAL_KNOWLEDGE_MARKERS = (
    "in general",
    "generally",
    "outside the document",
    "not from the document",
    "best practice",
    "best practices",
    "example",
    "examples",
    "khong theo tai lieu",
    "ngoai tai lieu",
)

PROFILE_SUMMARY_VARIANTS = (
    ("topic", "Focus: candidate profile, current role, and professional direction"),
    ("objective_problem", "Focus: objective, work experience, and responsibilities"),
    ("method", "Focus: skills, technologies, tools, and technical strengths"),
    ("results_contributions", "Focus: featured projects, achievements, and measurable outcomes"),
    ("limitations_scope", "Focus: education, certificates, interests, and supporting context"),
)
PROFILE_FIELD_VARIANTS = (
    ("profile_name", "Focus: candidate full name or identity line"),
    ("profile_current_role", "Focus: current role, headline, or target position"),
    ("profile_contacts", "Focus: email, phone, GitHub, LinkedIn, and contact channels"),
    ("profile_skills", "Focus: skills, tools, technologies, frameworks, and languages"),
    ("profile_experience", "Focus: work experience, companies, responsibilities, and tenure"),
    ("profile_projects", "Focus: projects, products, achievements, and measurable outcomes"),
    ("profile_education", "Focus: education, universities, majors, and academic background"),
    ("profile_certifications", "Focus: certifications, courses, licenses, and credentials"),
)
GENERIC_FIELD_VARIANTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "contact_identifiers",
        ("contact", "email", "phone", "github", "linkedin", "author", "owner", "maintainer"),
        "Focus: direct identifiers such as people, organizations, emails, phones, URLs, and ownership labels",
    ),
    (
        "skills_capabilities",
        ("skill", "skills", "tool", "technology", "framework", "language", "stack", "capability"),
        "Focus: capabilities, technologies, tools, frameworks, and technical keywords",
    ),
    (
        "roles_organizations",
        ("company", "organization", "department", "team", "vendor", "customer", "party", "role", "title"),
        "Focus: roles, parties, organizations, companies, teams, and named actors",
    ),
    (
        "procedures_steps",
        ("step", "steps", "procedure", "workflow", "setup", "install", "configuration", "instruction", "guide"),
        "Focus: step-by-step procedures, setup, workflow, operating instructions, and ordered actions",
    ),
    (
        "requirements_conditions",
        ("requirement", "requirements", "must", "shall", "condition", "criteria", "clause", "term", "obligation"),
        "Focus: requirements, obligations, conditions, clauses, acceptance criteria, and policy constraints",
    ),
    (
        "dates_timeline",
        ("date", "deadline", "duration", "period", "timeline", "schedule", "year", "month", "quarter", "tenure"),
        "Focus: dates, durations, deadlines, timelines, periods, and chronological markers",
    ),
    (
        "metrics_amounts",
        ("result", "results", "metric", "metrics", "accuracy", "score", "performance", "amount", "budget", "total"),
        "Focus: results, metrics, quantities, amounts, scores, and measured outcomes",
    ),
)


def detect_retrieval_intent(query: str) -> RetrievalIntent:
    normalized = query.strip().lower()

    if any(marker in normalized for marker in COMPARE_MARKERS):
        return RetrievalIntent.compare
    if any(marker in normalized for marker in SUMMARY_MARKERS):
        return RetrievalIntent.summary
    if any(marker in normalized for marker in EXTRACT_MARKERS):
        return RetrievalIntent.extract
    if any(marker in normalized for marker in MULTI_HOP_MARKERS):
        return RetrievalIntent.multi_hop
    if any(marker in normalized for marker in DEFINITION_MARKERS):
        return RetrievalIntent.definition
    if any(marker in normalized for marker in FACTUAL_MARKERS):
        return RetrievalIntent.factual
    return RetrievalIntent.question


def build_query_variants(
    query: str,
    plan: RetrievalPlan,
    alternate_queries: list[str] | None = None,
) -> tuple[tuple[str, str], ...]:
    variants: list[tuple[str, str]] = []
    normalized_alternates = [
        item.strip()
        for item in (alternate_queries or [])
        if item and item.strip() and item.strip() != query.strip()
    ]
    variants.extend(("rewrite", item) for item in normalized_alternates)
    variants.extend(plan.query_variants)
    return tuple(variants)


def is_profile_query(query: str) -> bool:
    normalized = query.strip().lower()
    return any(marker in normalized for marker in CV_REFERENCE_MARKERS)


def build_profile_query_variants(query: str) -> tuple[tuple[str, str], ...]:
    return tuple((label, f"{query}\n{instruction}") for label, instruction in PROFILE_FIELD_VARIANTS)


def is_exhaustive_query(query: str) -> bool:
    normalized = query.strip().lower()
    return any(marker in normalized for marker in EXHAUSTIVE_MARKERS)


def build_generic_field_query_variants(query: str) -> tuple[tuple[str, str], ...]:
    normalized = query.strip().lower()
    variants: list[tuple[str, str]] = []
    for label, markers, instruction in GENERIC_FIELD_VARIANTS:
        if any(marker in normalized for marker in markers):
            variants.append((label, f"{query}\n{instruction}"))
    return tuple(variants)


def build_exhaustive_query_variants(query: str) -> tuple[tuple[str, str], ...]:
    return (
        (
            "coverage_headings",
            f"{query}\nFocus: section headings, outlines, table labels, and topic transitions across the document.",
        ),
        (
            "coverage_entities",
            f"{query}\nFocus: exact terms, named entities, dates, numbers, identifiers, and repeated mentions.",
        ),
        (
            "coverage_lists",
            f"{query}\nFocus: lists, bullet points, tables, enumerations, and spread-out supporting mentions.",
        ),
    )


def infer_target_block_types(query: str, intent: RetrievalIntent) -> tuple[str, ...]:
    normalized = query.strip().lower()
    block_types = {
        "body",
        "introduction",
        "method",
        "results",
    }

    if intent == RetrievalIntent.summary:
        block_types.update(
            {
                "abstract",
                "problem_statement",
                "conclusion",
                "limitations_scope",
                "procedure",
                "requirements",
                "timeline",
                "legal_clause",
                "skills",
                "experience",
                "project",
                "education",
                "certification",
                "current_role",
            }
        )
    if intent in {RetrievalIntent.definition, RetrievalIntent.question, RetrievalIntent.multi_hop}:
        block_types.update({"abstract", "problem_statement", "conclusion", "procedure"})
    if intent == RetrievalIntent.extract:
        block_types.update({"procedure", "requirements", "timeline", "legal_clause"})

    if any(marker in normalized for marker in ("step", "procedure", "instruction", "setup", "install", "workflow")):
        block_types.update({"procedure", "method"})
    if any(marker in normalized for marker in ("requirement", "must", "shall", "condition", "clause", "term", "policy")):
        block_types.update({"requirements", "legal_clause"})
    if any(marker in normalized for marker in ("date", "deadline", "duration", "timeline", "schedule", "year", "month")):
        block_types.update({"timeline", "experience", "results"})
    if any(marker in normalized for marker in ("contact", "email", "phone", "github", "linkedin")):
        block_types.add("contact")
    if any(marker in normalized for marker in ("skill", "technology", "tool", "framework", "language")):
        block_types.update({"skills", "project", "experience"})
    if any(marker in normalized for marker in ("education", "degree", "university", "major", "certificate", "certification")):
        block_types.update({"education", "certification"})
    if any(marker in normalized for marker in ("company", "organization", "vendor", "customer", "party", "role", "title")):
        block_types.update({"experience", "current_role", "legal_clause"})

    return tuple(block_types)


def classify_query_scope(
    query: str,
    intent: RetrievalIntent,
    *,
    has_active_document_scope: bool,
) -> tuple[str, bool, str, str | None]:
    normalized = query.strip().lower()
    explicit_document_reference = any(marker in normalized for marker in DOCUMENT_REFERENCE_MARKERS)
    cv_reference = any(marker in normalized for marker in CV_REFERENCE_MARKERS)
    explicit_general = any(marker in normalized for marker in GENERAL_KNOWLEDGE_MARKERS)
    strong_document_signal = any(marker in normalized for marker in DOCUMENT_CONTENT_MARKERS)
    content_request = (
        intent in {RetrievalIntent.summary, RetrievalIntent.compare, RetrievalIntent.extract}
        or strong_document_signal
    )

    if cv_reference and content_request:
        reason = "CV or resume attributes must come from uploaded document evidence."
    elif explicit_document_reference and content_request:
        reason = "The query explicitly asks about uploaded document content."
    elif has_active_document_scope and intent in {
        RetrievalIntent.summary,
        RetrievalIntent.compare,
        RetrievalIntent.extract,
    } and not explicit_general:
        reason = "An active document is selected and the query asks for document-grounded content."
    elif has_active_document_scope and strong_document_signal and not explicit_general:
        reason = "An active document is selected and the query asks for factual document attributes."
    elif explicit_document_reference or cv_reference:
        reason = "The query is framed as a question about a specific uploaded document."
    else:
        return (
            "general-allowed",
            False,
            "The query looks like general knowledge and does not clearly depend on uploaded documents.",
            None,
        )

    return (
        "document-targeted",
        True,
        reason,
        "Outside knowledge stayed blocked because the query targets uploaded document content.",
    )


def build_retrieval_plan(
    query: str,
    active_document_count: int,
    has_active_document_scope: bool | None = None,
) -> RetrievalPlan:
    intent = detect_retrieval_intent(query)
    profile_query = is_profile_query(query)
    exhaustive_mode = is_exhaustive_query(query)
    balanced = active_document_count > 1
    document_scope = active_document_count > 0 if has_active_document_scope is None else has_active_document_scope
    (
        query_classification,
        document_target_required,
        classification_reason,
        outside_knowledge_blocked_reason,
    ) = classify_query_scope(
        query,
        intent,
        has_active_document_scope=document_scope,
    )
    base_kwargs = {
        "query_classification": query_classification,
        "document_target_required": document_target_required,
        "classification_reason": classification_reason,
        "outside_knowledge_blocked_reason": outside_knowledge_blocked_reason,
        "exhaustive_mode": exhaustive_mode,
    }
    generic_field_variants = list(build_generic_field_query_variants(query))
    profile_variants = list(build_profile_query_variants(query)) if profile_query else []
    exhaustive_variants = list(build_exhaustive_query_variants(query)) if exhaustive_mode else []
    target_block_types = infer_target_block_types(query, intent)

    if intent == RetrievalIntent.summary:
        query_variants = [
            ("topic", f"{query}\nFocus: topic, thesis title, and overall subject"),
            ("objective_problem", f"{query}\nFocus: objective, problem statement, and scope"),
            ("method", f"{query}\nFocus: method, model, algorithm, or approach"),
            (
                "results_contributions",
                f"{query}\nFocus: results, contributions, evaluation, and findings",
            ),
            (
                "limitations_scope",
                f"{query}\nFocus: limitations, scope, constraints, and conclusion",
            ),
        ]
        if profile_query:
            query_variants = [
                *[(label, f"{query}\n{instruction}") for label, instruction in PROFILE_SUMMARY_VARIANTS],
                *query_variants,
            ]
        return RetrievalPlan(
            intent=intent,
            top_k_search=40 if exhaustive_mode else 32,
            top_k_rerank=14 if exhaustive_mode else 12,
            confidence_threshold=0.12 if exhaustive_mode else 0.18,
            context_max_tokens=5200 if exhaustive_mode else 4400,
            prefer_document_order=True,
            balanced_per_document=balanced,
            ordered_document_scan=exhaustive_mode,
            summary_axes=SUMMARY_AXES,
            target_block_types=target_block_types,
            query_variants=tuple(query_variants + generic_field_variants + profile_variants + exhaustive_variants),
            require_multi_section=True,
            low_support_hint="Summary evidence did not cover enough major sections of the document.",
            coverage_min_sections=4 if exhaustive_mode else 3,
            **base_kwargs,
        )

    if intent == RetrievalIntent.compare:
        return RetrievalPlan(
            intent=intent,
            top_k_search=36 if exhaustive_mode else 30,
            top_k_rerank=12,
            confidence_threshold=0.24 if exhaustive_mode else 0.28,
            context_max_tokens=4600 if exhaustive_mode else 4200,
            balanced_per_document=balanced,
            ordered_document_scan=exhaustive_mode,
            target_block_types=target_block_types,
            query_variants=tuple(
                [
                    ("compare_topic", f"{query}\nFocus: main topic and scope"),
                    ("compare_method", f"{query}\nFocus: method, model, or technical approach"),
                    ("compare_results", f"{query}\nFocus: results, claims, and contributions"),
                ]
                + generic_field_variants
                + exhaustive_variants
            ),
            require_multi_section=balanced,
            low_support_hint="Comparison evidence was not balanced across the selected documents.",
            coverage_min_sections=3 if exhaustive_mode else 2,
            **base_kwargs,
        )

    if intent == RetrievalIntent.extract:
        return RetrievalPlan(
            intent=intent,
            top_k_search=36 if exhaustive_mode else 24,
            top_k_rerank=12 if exhaustive_mode else 8,
            confidence_threshold=0.24 if exhaustive_mode else 0.32,
            context_max_tokens=4600 if exhaustive_mode else 3200,
            prefer_document_order=exhaustive_mode,
            ordered_document_scan=exhaustive_mode,
            target_block_types=target_block_types,
            query_variants=tuple(generic_field_variants + profile_variants + exhaustive_variants),
            require_multi_section=exhaustive_mode,
            low_support_hint="The exact requested passage or list was not supported clearly enough in the document.",
            coverage_min_sections=4 if exhaustive_mode else 1,
            **base_kwargs,
        )

    if intent == RetrievalIntent.definition:
        return RetrievalPlan(
            intent=intent,
            top_k_search=24,
            top_k_rerank=8,
            confidence_threshold=0.3,
            context_max_tokens=3600,
            target_block_types=target_block_types,
            query_variants=(
                ("definition_intro", f"{query}\nFocus: explicit definition or introductory explanation"),
            ),
            low_support_hint="The document did not contain a clear definition or explicit explanatory statement.",
            **base_kwargs,
        )

    if intent == RetrievalIntent.multi_hop:
        return RetrievalPlan(
            intent=intent,
            top_k_search=30,
            top_k_rerank=10,
            confidence_threshold=0.28,
            context_max_tokens=4200,
            balanced_per_document=balanced,
            target_block_types=target_block_types,
            query_variants=tuple(
                [
                    ("multi_hop_problem", f"{query}\nFocus: problem statement, motivation, or scope"),
                    ("multi_hop_method", f"{query}\nFocus: method, model, or technical approach"),
                    ("multi_hop_results", f"{query}\nFocus: results, implications, or conclusion"),
                ]
                + generic_field_variants
                + exhaustive_variants
            ),
            require_multi_section=True,
            low_support_hint="The answer needs evidence from multiple sections, but retrieval did not find enough cross-section support.",
            coverage_min_sections=3 if exhaustive_mode else 2,
            **base_kwargs,
        )

    if intent == RetrievalIntent.factual:
        return RetrievalPlan(
            intent=intent,
            top_k_search=34 if exhaustive_mode else 26,
            top_k_rerank=12 if exhaustive_mode else 8,
            confidence_threshold=0.25 if exhaustive_mode else 0.33,
            context_max_tokens=4400 if exhaustive_mode else 3600,
            prefer_document_order=exhaustive_mode,
            ordered_document_scan=exhaustive_mode,
            target_block_types=target_block_types,
            query_variants=tuple(
                [
                    ("factual_method", f"{query}\nFocus: method, model, algorithm, or system design"),
                    ("factual_results", f"{query}\nFocus: findings, evaluation, or implementation details"),
                ]
                + generic_field_variants
                + profile_variants
                + exhaustive_variants
            ),
            low_support_hint="The main factual claim was not directly supported by technical sections of the document.",
            coverage_min_sections=3 if exhaustive_mode else 1,
            **base_kwargs,
        )

    return RetrievalPlan(
        intent=RetrievalIntent.question,
        top_k_search=34 if exhaustive_mode else 24,
        top_k_rerank=12 if exhaustive_mode else 8,
        confidence_threshold=0.26 if exhaustive_mode else 0.35,
        context_max_tokens=4400 if exhaustive_mode else 3800,
        prefer_document_order=exhaustive_mode,
        ordered_document_scan=exhaustive_mode,
        target_block_types=target_block_types,
        query_variants=tuple(generic_field_variants + profile_variants + exhaustive_variants),
        require_multi_section=exhaustive_mode,
        low_support_hint="The retrieved evidence was too weak or too diffuse to support a grounded answer.",
        coverage_min_sections=3 if exhaustive_mode else 1,
        **base_kwargs,
    )
