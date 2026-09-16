"""Environment-backed RAG settings with production fail-closed validation."""

from __future__ import annotations

import os
from dataclasses import dataclass

SUPPORTED_LOCALES = (
    "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "pa-IN", "od-IN",
)


def _int(env: dict[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _origins(env: dict[str, str], name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in env.get(name, "").split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    public_api_origin: str = "http://127.0.0.1:8000"
    public_ws_origin: str = "ws://127.0.0.1:8000/ws"
    cors_allowed_origins: tuple[str, ...] = ()
    ws_allowed_origins: tuple[str, ...] = ()
    supported_locales: tuple[str, ...] = SUPPORTED_LOCALES
    rag_top_k: int = 5
    rag_fetch_k: int = 20
    rag_total_deadline_ms: int = 200
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "echoquery_chunks_v1"
    qdrant_distance: str = "cosine"
    embedding_model: str = "hashing-baseline-test-v1"
    embedding_dimension: int = 64
    reranker_model: str = ""
    sarvam_api_key: str = ""
    sarvam_llm_base_url: str = "https://api.sarvam.ai"
    sarvam_llm_model: str = ""
    sarvam_llm_timeout_ms: int = 150
    sarvam_llm_max_retries: int = 0
    grounding_enabled: bool = True
    grounding_timeout_ms: int = 25
    max_query_chars: int = 2000
    log_format: str = "json"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = dict(os.environ if environ is None else environ)
        locales = tuple(item.strip() for item in env.get("SUPPORTED_LOCALES", ",".join(SUPPORTED_LOCALES)).split(",") if item.strip())
        unknown = set(locales) - set(SUPPORTED_LOCALES)
        if unknown or set(locales) != set(SUPPORTED_LOCALES):
            raise ValueError("SUPPORTED_LOCALES must contain exactly the eleven EchoQuery locales")
        return cls(
            app_env=env.get("APP_ENV", "development"),
            app_host=env.get("APP_HOST", "127.0.0.1"),
            app_port=_int(env, "APP_PORT", 8000),
            public_api_origin=env.get("PUBLIC_API_ORIGIN", "http://127.0.0.1:8000"),
            public_ws_origin=env.get("PUBLIC_WS_ORIGIN", "ws://127.0.0.1:8000/ws"),
            cors_allowed_origins=_origins(env, "CORS_ALLOWED_ORIGINS"),
            ws_allowed_origins=_origins(env, "WS_ALLOWED_ORIGINS"),
            supported_locales=locales,
            rag_top_k=_int(env, "RAG_TOP_K", 5),
            rag_fetch_k=_int(env, "RAG_FETCH_K", 20),
            rag_total_deadline_ms=_int(env, "RAG_TOTAL_DEADLINE_MS", 200),
            qdrant_url=env.get("QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=env.get("QDRANT_COLLECTION", "echoquery_chunks_v1"),
            qdrant_distance=env.get("QDRANT_DISTANCE", "cosine"),
            embedding_model=env.get("EMBEDDING_MODEL", "hashing-baseline-test-v1"),
            embedding_dimension=_int(env, "EMBEDDING_DIMENSION", 64),
            reranker_model=env.get("RERANKER_MODEL", ""),
            sarvam_api_key=env.get("SARVAM_API_KEY", ""),
            sarvam_llm_base_url=env.get("SARVAM_LLM_BASE_URL", "https://api.sarvam.ai"),
            sarvam_llm_model=env.get("SARVAM_LLM_MODEL", ""),
            sarvam_llm_timeout_ms=_int(env, "SARVAM_LLM_TIMEOUT_MS", 150),
            sarvam_llm_max_retries=_int(env, "SARVAM_LLM_MAX_RETRIES", 0),
            grounding_enabled=env.get("GROUNDING_ENABLED", "true").casefold() in {"1", "true", "yes"},
            grounding_timeout_ms=_int(env, "GROUNDING_TIMEOUT_MS", 25),
            max_query_chars=_int(env, "MAX_QUERY_CHARS", 2000),
            log_format=env.get("LOG_FORMAT", "json"),
        )

    def validate(self) -> None:
        if not 1 <= self.rag_top_k <= self.rag_fetch_k <= 20:
            raise ValueError("RAG_TOP_K and RAG_FETCH_K must satisfy 1 <= top_k <= fetch_k <= 20")
        if self.rag_total_deadline_ms <= 0:
            raise ValueError("RAG_TOTAL_DEADLINE_MS must be positive")
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be positive")
        if self.app_env == "production":
            required = {
                "PUBLIC_API_ORIGIN": self.public_api_origin,
                "PUBLIC_WS_ORIGIN": self.public_ws_origin,
                "SARVAM_API_KEY": self.sarvam_api_key,
                "SARVAM_LLM_MODEL": self.sarvam_llm_model,
            }
            missing = [name for name, value in required.items() if not value or "VERIFY_" in value or "REPLACE_" in value]
            if missing:
                raise ValueError(f"production settings contain unresolved values: {', '.join(missing)}")
            if not self.public_api_origin.startswith("https://") or not self.public_ws_origin.startswith("wss://"):
                raise ValueError("production public origins must use HTTPS/WSS")


__all__ = ["Settings", "SUPPORTED_LOCALES"]
