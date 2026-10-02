"""Custom exceptions for the Plant POC agent pipeline."""

from __future__ import annotations

import os
from typing import Any, Optional

_DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


class PetPlantError(Exception):
    """Base exception for all Pet Plant errors."""

    pass


class LLMUnavailableError(PetPlantError):
    """Raised when an LLM service or provider is unreachable, down, or fails to respond."""

    def __init__(
        self,
        message: str = "AI reasoning service (LLM) is currently unavailable.",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.original_error = original_error

    def to_error_dict(self, *, expose_details: bool | None = None) -> dict[str, Any]:
        """Format as standard BaseResponse error envelope.

        Args:
            expose_details: If ``True``, include raw error reason in the
                response.  Defaults to the ``DEBUG`` environment variable
                so that internal exception strings are never leaked in
                production.
        """
        should_expose = expose_details if expose_details is not None else _DEBUG
        details: dict[str, Any] = {}
        if self.provider:
            details["provider"] = self.provider
        if self.model:
            details["model"] = self.model
        if self.original_error and should_expose:
            details["reason"] = str(self.original_error)

        return {
            "success": False,
            "data": None,
            "message": self.message,
            "error": {
                "code": "LLM_UNAVAILABLE",
                "details": details or None,
            },
        }


class InternalServerError(PetPlantError):
    """Raised when an unhandled server, database, or pipeline fault occurs."""

    def __init__(
        self,
        message: str = "An unexpected internal server error occurred while processing the plant companion state.",
        request_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.original_error = original_error

    def to_error_dict(self, *, expose_details: bool | None = None) -> dict[str, Any]:
        """Format as standard BaseResponse error envelope.

        Args:
            expose_details: If ``True``, include raw error reason in the
                response.  Defaults to the ``DEBUG`` environment variable
                so that internal exception strings are never leaked in
                production.
        """
        should_expose = expose_details if expose_details is not None else _DEBUG
        details: dict[str, Any] = {}
        if self.request_id:
            details["request_id"] = self.request_id
        if self.original_error and should_expose:
            details["reason"] = str(self.original_error)

        return {
            "success": False,
            "data": None,
            "message": self.message,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "details": details or None,
            },
        }


def make_error_response(
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Helper creating a standard BaseResponse error envelope."""
    return {
        "success": False,
        "data": None,
        "message": message,
        "error": {
            "code": code,
            "details": details,
        },
    }
