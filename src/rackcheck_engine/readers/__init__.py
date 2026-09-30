"""Reader registry.

Each reader module defines a class implementing :class:`~.base.Reader` and registers it
here. Readers are added phase by phase (SPEC-01 section 7); a format with no registered
reader produces a ``READER_NOT_AVAILABLE`` error rather than an empty result.
"""

from __future__ import annotations

from ..detect import ProjectFormat
from .base import Reader

_REGISTRY: dict[ProjectFormat, Reader] = {}


def register(reader: Reader) -> None:
    for fmt in reader.formats:
        if fmt in _REGISTRY:
            raise ValueError(f"A reader for {fmt} is already registered")
        _REGISTRY[fmt] = reader


def reader_for(fmt: ProjectFormat) -> Reader | None:
    return _REGISTRY.get(fmt)


def supported_formats() -> list[ProjectFormat]:
    return sorted(_REGISTRY)


def _register_builtin() -> None:
    from .ableton import AbletonReader
    from .dawproject import DawprojectReader
    from .reaper import ReaperReader

    for reader in (ReaperReader(), AbletonReader(), DawprojectReader()):
        register(reader)


_register_builtin()
