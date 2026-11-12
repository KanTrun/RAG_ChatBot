import os

import pytest

from app.services.answer_brief_builder import build_answer_brief
from app.services.context_assembler import SourceReference
from app.services.embedding_service import (
    EmbeddingResult,
    OllamaEmbeddingService,
    OpenAIEmbeddingService,
)
from app.services.evidence_clusterer import (
    build_evidence_clusters,
    build_summary_subqueries,
    select_evidence_chunks,
)
from app.services.grounded_answer_fallback import build_grounded_fallback_answer
from app.services.reranking_service import RankedChunk, RerankingService
from app.services.retrieval_intent_service import (
    RetrievalIntent,
    build_retrieval_plan,
    detect_retrieval_intent,
)
from app.services.retrieval_section_policy import evaluate_chunk_policy
from app.services.retrieval_service import RetrievalService


class FakeEmbeddingService:
    @property
    def dimension(self) -> int:
        return 1024

    async def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        return [EmbeddingResult(dense=[0.1] * self.dimension) for _text in texts]


@pytest.mark.anyio
async def test_rrf_merge_prioritizes_chunks_seen_by_both_rankers():
    vector_results = [
        {"chunk_id": "a", "content": "vector one"},
        {"chunk_id": "shared", "content": "shared"},
    ]
    bm25_results = [
        {"chunk_id": "shared", "content": "shared"},
        {"chunk_id": "b", "content": "keyword two"},
    ]

    merged = RetrievalService._rrf_merge(vector_results, bm25_results)

    assert merged[0]["chunk_id"] == "shared"
    assert {item["chunk_id"] for item in merged} == {"a", "shared", "b"}


@pytest.mark.anyio
async def test_deduplicate_by_embedding_removes_near_duplicates():
    chunks = [
        {"chunk_id": "a", "embedding": [1.0, 0.0]},
        {"chunk_id": "b", "embedding": [0.99, 0.01]},
        {"chunk_id": "c", "embedding": [0.0, 1.0]},
    ]

    deduped = RetrievalService._deduplicate_by_embedding(chunks, threshold=0.95)

    assert [chunk["chunk_id"] for chunk in deduped] == ["a", "c"]


@pytest.mark.anyio
async def test_deduplicate_by_embedding_accepts_stringified_pgvector_embeddings():
    chunks = [
        {"chunk_id": "a", "embedding": "[1.0,0.0]"},
        {"chunk_id": "b", "embedding": "[0.99,0.01]"},
        {"chunk_id": "c", "embedding": "[0.0,1.0]"},
    ]

    deduped = RetrievalService._deduplicate_by_embedding(chunks, threshold=0.95)

    assert [chunk["chunk_id"] for chunk in deduped] == ["a", "c"]


@pytest.mark.anyio
async def test_ollama_embedding_service_returns_1024_dimensional_embeddings(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.25] * 1024]}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, json):
            assert url == "http://ollama:11434/api/embed"
            assert json == {"model": "mxbai-embed-large", "input": ["AlphaProject"]}
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    embeddings = await OllamaEmbeddingService().embed_texts(["AlphaProject"])

    assert len(embeddings) == 1
    assert len(embeddings[0].dense) == 1024
    assert embeddings[0].sparse is None


@pytest.mark.anyio
async def test_retrieval_returns_indexed_document_with_fake_embedding(
    db_session,
    indexed_document,
    test_user,
):
    service = RetrievalService(
        session=db_session,
        embedding_service=FakeEmbeddingService(),
    )

    result = await service.retrieve(
        query="AlphaProject hybrid retrieval citations",
        user_id=test_user.id,
        user_role_ids=[role.id for role in test_user.roles],
        top_k_search=5,
        top_k_rerank=3,
    )

    assert result.candidate_count >= 1
    assert "AlphaProject" in result.context.context_text
    assert result.context.diagnostics["bm25_used"] is True
    assert result.context.diagnostics["bm25_contributed"] is True


def test_how_does_query_is_classified_as_definition_not_multi_hop():
    """Bug 3 regression test: 'How does X work?' must be definition, not multi_hop."""
    assert detect_retrieval_intent("How does hybrid search work?") == RetrievalIntent.definition
    assert detect_retrieval_intent("How do RAG systems retrieve context?") == RetrievalIntent.definition

    plan = build_retrieval_plan("How does hybrid search work?", active_document_count=1)
    assert plan.intent == RetrievalIntent.definition
    assert plan.require_multi_section is False


def test_single_section_document_is_not_rejected_for_multi_section_plan():
    """Bug 3 regression test: single-section documents must not fail multi-section check."""
    plan = build_retrieval_plan("Why does the system combine BM25 and vector search?", active_document_count=1)
    assert plan.intent == RetrievalIntent.multi_hop
    assert plan.require_multi_section is True

    chunk = RankedChunk(
        chunk_id="c1",
        content="Hybrid search combines BM25 keyword retrieval and vector similarity.",
        score=0.73,
        original_rank=0,
        metadata={"section": "Document", "section_path": "Document", "block_type": "method"},
    )
    reason = RetrievalService._build_low_support_reason(
        plan=plan,
        confidence_chunks=[chunk],
        confidence_threshold=plan.confidence_threshold,
        selected_chunks=[chunk],
        available_section_count=1,
    )
    assert reason is None


def test_bm25_tsquery_builder_strips_question_words_and_focus_instructions():
    """Bug 4 regression test: BM25 query builder must strip question stopwords and Focus suffixes."""
    tsquery = RetrievalService._build_bm25_tsquery_string(
        "What is hybrid search?\nFocus: explicit definition or introductory explanation"
    )
    assert tsquery == "hybrid | search"

    how_tsquery = RetrievalService._build_bm25_tsquery_string("How does hybrid search work?")
    assert how_tsquery == "hybrid | search"


@pytest.mark.anyio
async def test_bm25_search_finds_chunks_when_query_contains_document_keywords(
    db_session,
    indexed_document,
    test_user,
):
    """Bug 4 regression test: _bm25_search must return non-empty results for keyword queries."""
    service = RetrievalService(
        session=db_session,
        embedding_service=FakeEmbeddingService(),
    )

    bm25_hits = await service._bm25_search(
        query="What is AlphaProject hybrid retrieval?",
        user_id=test_user.id,
        user_role_ids=[role.id for role in test_user.roles],
        filters=None,
        top_k=5,
    )

    assert len(bm25_hits) >= 1
    assert "AlphaProject" in bm25_hits[0]["content"]
    assert bm25_hits[0]["metadata"]["lexical_score"] > 0


def test_fallback_reranker_prefers_chunks_that_match_the_question():
    service = RerankingService()
    chunks = [
        {
            "id": "c1",
            "content": "This section describes database migrations and seed data.",
            "metadata": {"document_title": "Guide", "section": "Operations"},
        },
        {
            "id": "c2",
            "content": "Hybrid retrieval combines vector similarity with BM25 keyword matching.",
            "metadata": {"document_title": "Guide", "section": "Retrieval"},
        },
    ]

    ranked = service._fallback("How does hybrid retrieval work?", chunks, top_k=2)

    assert ranked[0].chunk_id == "c2"
    assert ranked[0].score > ranked[1].score


def test_build_retrieval_plan_uses_ordered_scan_for_summaries():
    plan = build_retrieval_plan("Summarize this document", active_document_count=2)

    assert plan.intent == RetrievalIntent.summary
    assert plan.ordered_document_scan is False
    assert plan.prefer_document_order is True
    assert plan.balanced_per_document is True
    assert "method" in plan.summary_axes
    assert plan.document_target_required is True
    assert plan.query_classification == "document-targeted"


def test_build_retrieval_plan_balances_compare_requests_for_multiple_documents():
    plan = build_retrieval_plan("Compare the two guides", active_document_count=2)

    assert plan.intent == RetrievalIntent.compare
    assert plan.balanced_per_document is True
    assert plan.ordered_document_scan is False


def test_build_retrieval_plan_treats_active_guide_queries_as_document_targeted():
    compare_plan = build_retrieval_plan(
        "Compare the two guides",
        active_document_count=2,
        has_active_document_scope=True,
    )
    summary_plan = build_retrieval_plan(
        "Summarize this guide",
        active_document_count=1,
        has_active_document_scope=True,
    )

    assert compare_plan.document_target_required is True
    assert compare_plan.query_classification == "document-targeted"
    assert summary_plan.document_target_required is True
    assert summary_plan.query_classification == "document-targeted"


def test_build_retrieval_plan_detects_factual_queries_and_prioritizes_technical_sections():
    plan = build_retrieval_plan("Which machine learning model does the project use?", active_document_count=1)

    assert plan.intent == RetrievalIntent.factual
    assert "method" in plan.target_block_types
    assert "results" in plan.target_block_types
    assert any(label == "factual_method" for label, _text in plan.query_variants)


def test_build_retrieval_plan_detects_definition_queries():
    plan = build_retrieval_plan("What is retrieval augmented generation?", active_document_count=1)

    assert plan.intent == RetrievalIntent.definition
    assert "abstract" in plan.target_block_types
    assert any(label == "definition_intro" for label, _text in plan.query_variants)
    assert plan.document_target_required is False
    assert plan.query_classification == "general-allowed"


def test_build_retrieval_plan_detects_multi_hop_queries():
    plan = build_retrieval_plan("How does the method affect the final results?", active_document_count=1)

    assert plan.intent == RetrievalIntent.multi_hop
    assert plan.require_multi_section is True
    assert any(label == "multi_hop_results" for label, _text in plan.query_variants)
    assert plan.document_target_required is True


def test_build_retrieval_plan_marks_cv_queries_as_document_targeted_without_active_scope():
    plan = build_retrieval_plan("What skills are listed in this CV?", active_document_count=0)

    assert plan.document_target_required is True
    assert plan.query_classification == "document-targeted"
    assert plan.outside_knowledge_blocked_reason is not None


def test_build_retrieval_plan_keeps_general_questions_general_even_with_active_documents():
    plan = build_retrieval_plan(
        "How does caching work?",
        active_document_count=1,
        has_active_document_scope=True,
    )

    assert plan.document_target_required is False
    assert plan.query_classification == "general-allowed"


def test_build_retrieval_plan_uses_profile_variants_as_an_adapter_not_a_separate_core_path():
    plan = build_retrieval_plan("Tom tat CV nay", active_document_count=1)

    assert plan.intent == RetrievalIntent.summary
    assert plan.require_multi_section is True
    assert plan.document_target_required is True
    assert "skills" in plan.target_block_types
    assert any(label == "profile_skills" for label, _text in plan.query_variants)
    assert any(label == "topic" for label, _text in plan.query_variants)


def test_build_retrieval_plan_enables_exhaustive_mode_for_full_list_queries():
    plan = build_retrieval_plan("List all information mentioned in this document", active_document_count=1)

    assert plan.exhaustive_mode is True
    assert plan.ordered_document_scan is True
    assert plan.coverage_min_sections >= 3


def test_section_policy_penalizes_acknowledgements_for_normal_questions():
    policy = evaluate_chunk_policy(
        "What does the proposed system architecture do?",
        "Loi cam on co the hien su biet on den giang vien huong dan.",
        {"section": "Loi cam on", "chunk_index": 4},
    )

    assert policy.kind == "acknowledgement"
    assert policy.relevance_bias < 0


def test_section_policy_keeps_figure_captions_when_query_explicitly_targets_them():
    policy = evaluate_chunk_policy(
        "Explain figure 2 and what it shows",
        "Figure 2. Retrieval pipeline and reranking flow.",
        {"section": "Results", "chunk_index": 12},
    )

    assert policy.kind == "figure_caption"
    assert policy.relevance_bias > 0


def test_retrieval_service_section_policy_demotes_boilerplate_chunks():
    chunks = [
        {
            "chunk_id": "ack",
            "content": "Acknowledgement. We thank our teachers and family for support.",
            "rrf_score": 0.9,
            "metadata": {"section": "Acknowledgement", "chunk_index": 2},
        },
        {
            "chunk_id": "body",
            "content": "The system uses hybrid retrieval that combines vector search with BM25.",
            "rrf_score": 0.7,
            "metadata": {"section": "Method", "chunk_index": 10},
        },
    ]

    ranked = RetrievalService._apply_section_policy(
        "How does the system retrieve information?",
        chunks,
    )

    assert ranked[0]["chunk_id"] == "body"
    assert ranked[0]["metadata"]["section_kind"] == "method"
    assert ranked[1]["metadata"]["section_kind"] == "acknowledgement"


def test_section_policy_prefers_explicit_block_type_metadata():
    policy = evaluate_chunk_policy(
        "Summarize the methodology",
        "The paper thanks advisors and faculty.",
        {
            "section": "Appendix",
            "block_type": "method",
            "section_path": "Document > Method",
        },
    )

    assert policy.kind == "method"
    assert policy.relevance_bias > 0


def test_section_policy_detects_procedure_sections_for_manual_like_queries():
    policy = evaluate_chunk_policy(
        "What are the setup steps in this guide?",
        "Installation steps: first configure the server, then restart the service.",
        {"section": "Setup Guide", "chunk_index": 8},
    )

    assert policy.kind == "procedure"
    assert policy.relevance_bias > 0


def test_build_summary_subqueries_covers_fixed_summary_axes():
    subqueries = build_summary_subqueries("Tom tat de tai nay")

    assert [label for label, _query in subqueries] == [
        "topic",
        "objective_problem",
        "method",
        "results_contributions",
        "limitations_scope",
    ]


def test_summary_evidence_selection_prefers_structural_coverage_over_boilerplate():
    ranked_chunks = [
        RankedChunk(
            chunk_id="ack",
            content="Acknowledgement. Thanks to the supervisors.",
            score=0.99,
            original_rank=0,
            metadata={
                "block_type": "acknowledgement",
                "section_path": "Document > Acknowledgement",
                "document_id": "doc-1",
                "parent_block_id": "ack-parent",
                "query_labels": ["topic"],
            },
        ),
        RankedChunk(
            chunk_id="method",
            content="The system uses parent-child retrieval with evidence clustering.",
            score=0.82,
            original_rank=1,
            metadata={
                "block_type": "method",
                "section_path": "Document > Method",
                "document_id": "doc-1",
                "parent_block_id": "method-parent",
                "query_labels": ["method"],
            },
        ),
        RankedChunk(
            chunk_id="results",
            content="The system reduces unsupported claims in summary answers.",
            score=0.8,
            original_rank=2,
            metadata={
                "block_type": "results",
                "section_path": "Document > Results",
                "document_id": "doc-1",
                "parent_block_id": "results-parent",
                "query_labels": ["results_contributions"],
            },
        ),
    ]

    clusters = build_evidence_clusters(ranked_chunks)
    selected, diagnostics = select_evidence_chunks("summary", clusters, top_k=3)

    assert [chunk.chunk_id for chunk in selected[:2]] == ["method", "results"]
    assert "method" in diagnostics["summary_axes_covered"]
    assert all(chunk.metadata.get("block_type") != "acknowledgement" for chunk in selected[:2])


def test_answer_brief_marks_missing_summary_slots_explicitly():
    brief = build_answer_brief(
        "summary",
        [
            SourceReference(
                citation_number=1,
                document_title="Alpha Guide",
                file_name="alpha.txt",
                page_number=1,
                section="Method",
                section_path="Alpha Guide > Method",
                block_type="method",
                chunk_id="chunk-1",
                score=0.98,
                excerpt="Parent-child retrieval is the main method.",
                answer_section="method",
            )
        ],
    )

    assert brief is not None
    assert "Phuong phap chinh" in brief
    assert "khong tim thay du bang chung" in brief


def test_answer_brief_uses_profile_summary_labels_for_cv_queries():
    brief = build_answer_brief(
        "summary",
        [
            SourceReference(
                citation_number=1,
                document_title="Candidate CV",
                file_name="cv.pdf",
                page_number=1,
                section="Skills",
                section_path="Candidate CV > Skills",
                block_type="body",
                chunk_id="chunk-1",
                score=0.72,
                excerpt="Python, TypeScript, PostgreSQL, Docker",
                answer_section="method",
            )
        ],
        query="Tom tat CV nay",
    )

    assert brief is not None
    assert "Profile overview" in brief
    assert "Skills and technology" in brief
    assert "Question focus: Tom tat CV nay" in brief


def test_answer_brief_marks_low_support_for_factual_questions():
    brief = build_answer_brief(
        "factual",
        [],
        query="Which model is used?",
        low_confidence=True,
    )

    assert brief is not None
    assert "Question focus: Which model is used?" in brief
    assert "insufficient evidence" in brief


def test_grounded_fallback_answer_is_structured_and_cited():
    answer = build_grounded_fallback_answer(
        "How does hybrid retrieval work?",
        (
            "[1] Source: Guide\n"
            "Hybrid retrieval combines vector similarity with BM25 keyword search.\n"
            "[2] Source: Guide\n"
            "The reranking stage then prioritizes the most relevant evidence.\n"
        ),
    )

    assert answer is not None
    assert "According to the retrieved document context" in answer
    assert "[1]" in answer


@pytest.mark.anyio
async def test_ollama_embedding_service_rejects_dimension_mismatch(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embeddings": [[0.25] * 768]}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    with pytest.raises(ValueError, match="returned 768 dimensions; expected 1024"):
        await OllamaEmbeddingService().embed_texts(["AlphaProject"])


@pytest.mark.anyio
async def test_ollama_embedding_service_falls_back_when_provider_unreachable(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise OSError("Name or service not known")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    embeddings = await OllamaEmbeddingService().embed_texts(["AlphaProject"])

    assert len(embeddings) == 1
    assert len(embeddings[0].dense) == 1024


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Real embedding retrieval requires OPENAI_API_KEY",
)
@pytest.mark.anyio
async def test_retrieval_returns_indexed_document_with_real_embedding(
    db_session,
    indexed_document,
    test_user,
):
    service = RetrievalService(
        session=db_session,
        embedding_service=OpenAIEmbeddingService(),
    )

    result = await service.retrieve(
        query="AlphaProject hybrid retrieval citations",
        user_id=test_user.id,
        user_role_ids=[role.id for role in test_user.roles],
        top_k_search=5,
        top_k_rerank=3,
    )

    assert result.candidate_count >= 1
    assert "AlphaProject" in result.context.context_text
