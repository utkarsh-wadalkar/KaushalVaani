"""Request validation and basic prompt-injection/safety guardrails."""

from __future__ import annotations

from generation.schemas import Query, SUPPORTED_LOCALES


class InputGuardError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


UNSAFE_MARKERS = (
    "ignore previous instructions",
    "reveal the system prompt",
    "jailbreak",
    "developer message",
)


def validate_query(value: Query | dict) -> Query:
    if isinstance(value, Query):
        query = value
    elif isinstance(value, dict):
        language = value.get("language")
        if language not in SUPPORTED_LOCALES:
            raise InputGuardError("UNSUPPORTED_LANGUAGE", "language is unsupported")
        try:
            query = Query(**value)
        except (TypeError, ValueError) as error:
            raise InputGuardError("INVALID_REQUEST", str(error)) from error
    else:
        raise InputGuardError("INVALID_REQUEST", "query must be an object")
    lowered = query.query.casefold()
    if any(marker in lowered for marker in UNSAFE_MARKERS):
        raise InputGuardError("INVALID_REQUEST", "query contains an unsafe instruction")
    if len(query.query) > 2_000:
        raise InputGuardError("INVALID_REQUEST", "query exceeds the maximum length")
    return query
