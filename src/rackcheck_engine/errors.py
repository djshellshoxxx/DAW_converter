"""Engine error type with stable codes (SPEC-03 section 7)."""

from __future__ import annotations

from typing import Any


class EngineError(Exception):
    """An error the GUI and CLI can show in plain language.

    ``code`` is stable and maps to the user-facing messages in SPEC-03 section 5.
    """

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


# Stable error codes. Add new codes here; never rename an existing one.
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
READER_NOT_AVAILABLE = "READER_NOT_AVAILABLE"
PATH_NOT_FOUND = "PATH_NOT_FOUND"
NO_PROJECT_FOUND = "NO_PROJECT_FOUND"
ARCHIVE_REJECTED = "ARCHIVE_REJECTED"
CORRUPT_PROJECT = "CORRUPT_PROJECT"
INVENTORY_UNREADABLE = "INVENTORY_UNREADABLE"
READER_TIMEOUT = "READER_TIMEOUT"

# Codes used by the GUI bridge (SPEC-03 sections 5 and 7).
INVALID_ARGUMENT = "INVALID_ARGUMENT"
PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
BUSY = "BUSY"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
REPORT_INVALID = "REPORT_INVALID"
MULTIPLE_PROJECTS = "MULTIPLE_PROJECTS"
EXPORT_FAILED = "EXPORT_FAILED"
NOT_AVAILABLE = "NOT_AVAILABLE"
INTERNAL_ERROR = "INTERNAL_ERROR"
