"""Startup provider validation, Ollama model verification, warmup, and component health checks."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_OPENAI_MODEL_PREFIXES = ("gpt-", "o1-", "o3-", "text-embedding-")


class ProviderConfigurationError(RuntimeError):
    """Raised when provider or model configuration is invalid at startup."""


def validate_provider_settings(settings: Settings | None = None) -> list[str]:
    """Validate provider/model combinations and return a list of configuration errors."""
    cfg = settings or get_settings()
    errors: list[str] = []

    if cfg.embedding_provider == "openai" and not cfg.openai_api_key:
        errors.append(
            "EMBEDDING_PROVIDER is set to 'openai' but OPENAI_API_KEY is empty. "
            "Set EMBEDDING_PROVIDER=ollama for local embeddings or provide OPENAI_API_KEY."
        )
    if cfg.llm_provider == "openai" and not cfg.openai_api_key:
        errors.append(
            "LLM_PROVIDER is set to 'openai' but OPENAI_API_KEY is empty. "
            "Set LLM_PROVIDER=ollama and LLM_MODEL=qwen2.5:7b for local LLM or provide OPENAI_API_KEY."
        )
    if cfg.llm_provider == "anthropic" and not cfg.anthropic_api_key:
        errors.append("LLM_PROVIDER is set to 'anthropic' but ANTHROPIC_API_KEY is empty.")
    if cfg.llm_provider == "gemini" and not cfg.gemini_api_key:
        errors.append("LLM_PROVIDER is set to 'gemini' but GEMINI_API_KEY is empty.")

    if cfg.llm_provider == "ollama":
        if not cfg.ollama_base_url:
            errors.append("LLM_PROVIDER is 'ollama' but OLLAMA_BASE_URL is empty.")
        if cfg.llm_model.startswith(_OPENAI_MODEL_PREFIXES):
            errors.append(
                f"LLM_PROVIDER is 'ollama' but LLM_MODEL='{cfg.llm_model}' looks like an OpenAI model name. "
                "Use an Ollama model such as 'qwen2.5:7b'."
            )

    if cfg.embedding_provider == "ollama":
        if not cfg.ollama_base_url:
            errors.append("EMBEDDING_PROVIDER is 'ollama' but OLLAMA_BASE_URL is empty.")
        if not cfg.ollama_embedding_model:
            errors.append("EMBEDDING_PROVIDER is 'ollama' but OLLAMA_EMBEDDING_MODEL is empty.")
        elif cfg.ollama_embedding_model.startswith(_OPENAI_MODEL_PREFIXES):
            errors.append(
                f"EMBEDDING_PROVIDER is 'ollama' but OLLAMA_EMBEDDING_MODEL='{cfg.ollama_embedding_model}' "
                "looks like an OpenAI model name. Use 'mxbai-embed-large'."
            )

    return errors


def _model_matches(installed_names: set[str], target_model: str) -> bool:
    """Match Ollama model names with or without ':latest' tag."""
    normalized = target_model.strip()
    if normalized in installed_names:
        return True
    if ":" not in normalized and f"{normalized}:latest" in installed_names:
        return True
    base_names = {name.split(":")[0] for name in installed_names}
    if ":" not in normalized and normalized in base_names:
        return True
    return False


async def check_ollama_models(settings: Settings | None = None, timeout: float = 5.0) -> dict[str, Any]:
    """Query Ollama /api/tags to verify reachability and check required models."""
    cfg = settings or get_settings()
    uses_ollama = "ollama" in {cfg.embedding_provider, cfg.llm_provider}
    if not uses_ollama:
        return {
            "status": "skipped",
            "reachable": True,
            "required_models": [],
            "missing_models": [],
            "installed_models": [],
        }

    required_models: list[str] = []
    if cfg.embedding_provider == "ollama" and cfg.ollama_embedding_model:
        required_models.append(cfg.ollama_embedding_model)
    if cfg.llm_provider == "ollama" and cfg.llm_model:
        required_models.append(cfg.llm_model)

    base_url = cfg.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("Failed to reach Ollama at %s: %s", base_url, exc)
        return {
            "status": "unreachable",
            "reachable": False,
            "base_url": base_url,
            "required_models": required_models,
            "missing_models": required_models,
            "installed_models": [],
            "error": str(exc),
        }

    models_list = payload.get("models") or []
    installed_names = {
        str(item.get("name") or item.get("model") or "").strip()
        for item in models_list
        if isinstance(item, dict) and (item.get("name") or item.get("model"))
    }
    missing = [m for m in required_models if not _model_matches(installed_names, m)]

    if missing:
        pull_cmds = " && ".join(f"ollama pull {m}" for m in missing)
        logger.error(
            "Ollama is running at %s but required model(s) %s are missing! Installed: %s. Run: %s",
            base_url,
            missing,
            sorted(installed_names),
            pull_cmds,
        )
        return {
            "status": "missing_models",
            "reachable": True,
            "base_url": base_url,
            "required_models": required_models,
            "missing_models": missing,
            "installed_models": sorted(installed_names),
            "error": f"Missing Ollama models: {', '.join(missing)}. Run: {pull_cmds}",
        }

    return {
        "status": "healthy",
        "reachable": True,
        "base_url": base_url,
        "required_models": required_models,
        "missing_models": [],
        "installed_models": sorted(installed_names),
    }


async def warmup_ollama_models(app_state: Any, settings: Settings | None = None) -> dict[str, Any]:
    """Warm up Ollama LLM and embedding models on startup so CPU first-token latency is minimized."""
    cfg = settings or get_settings()
    app_state.model_warmup_status = "warming_up"
    app_state.model_warmup_error = None
    start = time.time()

    check = await check_ollama_models(cfg, timeout=8.0)
    app_state.ollama_check = check
    if not check.get("reachable"):
        app_state.model_warmup_status = "unreachable"
        app_state.model_warmup_error = check.get("error")
        return check

    if check.get("missing_models"):
        app_state.model_warmup_status = "missing_models"
        app_state.model_warmup_error = check.get("error")
        if cfg.strict_startup_model_check:
            raise ProviderConfigurationError(str(check.get("error")))
        return check

    base_url = cfg.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            if cfg.embedding_provider == "ollama" and cfg.ollama_embedding_model:
                await client.post(
                    f"{base_url}/api/embed",
                    json={"model": cfg.ollama_embedding_model, "input": ["warmup"]},
                )
            if cfg.llm_provider == "ollama" and cfg.llm_model:
                await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": cfg.llm_model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "options": {"num_predict": 1, "temperature": 0.0},
                    },
                )
        elapsed_ms = int((time.time() - start) * 1000)
        app_state.model_warmup_status = "ready"
        app_state.model_warmup_ms = elapsed_ms
        logger.info("Ollama model warmup completed in %sms", elapsed_ms)
        return {**check, "warmup_status": "ready", "warmup_ms": elapsed_ms}
    except Exception as exc:
        logger.warning("Ollama model warmup did not finish cleanly: %s", exc)
        app_state.model_warmup_status = "degraded"
        app_state.model_warmup_error = str(exc)
        return {**check, "warmup_status": "degraded", "error": str(exc)}
