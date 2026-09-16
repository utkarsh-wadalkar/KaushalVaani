"""Provider-neutral STT boundary and deterministic fixture adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


SUPPORTED_LOCALES = (
    "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "pa-IN", "od-IN",
)


@dataclass(frozen=True, slots=True)
class Transcript:
    request_id: str
    text: str
    language: str
    is_final: bool
    provider: str
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "text": self.text,
            "language": self.language,
            "is_final": self.is_final,
            "provider": self.provider,
            "confidence": self.confidence,
        }


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, *, request_id: str, language: str | None) -> Transcript: ...


class FixtureSTT:
    """Treat UTF-8 bytes as transcript text for local demos and tests."""

    provider = "fixture"

    def transcribe(self, audio: bytes, *, request_id: str, language: str | None) -> Transcript:
        text = audio.decode("utf-8").strip()
        if not text:
            raise ValueError("fixture audio payload is empty")
        resolved_language = language or "en-IN"
        if resolved_language not in SUPPORTED_LOCALES:
            raise ValueError("unsupported language")
        return Transcript(request_id, text, resolved_language, True, self.provider, 1.0)
