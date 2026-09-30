"""Reader interface (SPEC-01 Phase 0, SPEC-02 section 8).

Rules every reader follows:
- Open the source read-only and never write to it (SPEC-01 P3).
- Leave unknown fields ``None``; never guess (SPEC-01 P4).
- Tag every plugin with a :class:`~rackcheck_engine.model.Confidence`.
- Bound memory and bounds-check every length field; corrupt input raises
  ``EngineError(CORRUPT_PROJECT)``, never an unhandled exception (SPEC-07 section 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..detect import ProjectFormat
from ..model import Confidence, ScanResult


@runtime_checkable
class Reader(Protocol):
    #: Formats this reader handles.
    formats: tuple[ProjectFormat, ...]
    #: SemVer of the reader, copied into ``ScanResult.source.reader_version``.
    version: str

    def can_read(self, path: Path) -> Confidence | None:
        """How confident this reader is that it can read ``path``; None if it can't."""
        ...

    def read(self, path: Path) -> ScanResult:
        """Parse ``path`` into the common data model."""
        ...
