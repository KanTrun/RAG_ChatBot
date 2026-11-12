import pytest

from app.config import Settings
from app.services.provider_health import check_ollama_models, validate_provider_settings


@pytest.mark.anyio
async def test_health_endpoint_returns_status_and_components(async_client):
    response = await async_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "components" in data
    assert set(data["components"].keys()) >= {"database", "redis", "ollama", "celery_worker"}
    assert data["components"]["celery_worker"]["ingestion_task_registered"] is True


def test_validate_provider_settings_detects_mismatched_provider_and_model():
    """Bug 2 regression test: catch OpenAI model name when provider is ollama or missing API key."""
    bad_ollama = Settings(
        embedding_provider="ollama",
        ollama_embedding_model="mxbai-embed-large",
        llm_provider="ollama",
        llm_model="gpt-4o-mini",
    )
    errors = validate_provider_settings(bad_ollama)
    assert any("gpt-4o-mini" in err for err in errors)

    good_ollama = Settings(
        embedding_provider="ollama",
        ollama_embedding_model="mxbai-embed-large",
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
    )
    assert validate_provider_settings(good_ollama) == []


@pytest.mark.anyio
async def test_check_ollama_models_reports_missing_models(monkeypatch):
    """Bug 2 regression test: startup check must report missing Ollama models clearly."""
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "mxbai-embed-large:latest"}]}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    cfg = Settings(
        embedding_provider="ollama",
        ollama_embedding_model="mxbai-embed-large",
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
    )
    result = await check_ollama_models(cfg)
    assert result["status"] == "missing_models"
    assert "qwen2.5:7b" in result["missing_models"]
