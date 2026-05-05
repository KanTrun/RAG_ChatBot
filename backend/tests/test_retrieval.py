import os

import pytest

from app.services.answer_brief_builder import build_answer_brief
from app.services.context_assembler import SourceReference
from app.services.evidence_clusterer import build_evidence_clusters, build_summary_subqueries, select_evidence_chunks
from app.services.embedding_service import EmbeddingResult, OllamaEmbeddingService, OpenAIEmbeddingService
from app.services.grounded_answer_fallback import build_grounded_fallback_answer
from app.services.reranking_service import RerankingService
from app.services.reranking_service import RankedChunk
from app.services.retrieval_intent_service import RetrievalIntent, build_retrieval_plan
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


def test_build_retrieval_plan_balances_compare_requests_for_multiple_documents():
    plan = build_retrieval_plan("Compare the two guides", active_document_count=2)

    assert plan.intent == RetrievalIntent.compare
    assert plan.balanced_per_document is True
    assert plan.ordered_document_scan is False


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
