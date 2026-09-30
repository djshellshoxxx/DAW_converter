"""Shared scan path used by both the CLI and the GUI bridge (SPEC-03 section 7).

``scan_candidate`` turns one detected project into either a full report or a stable
error entry. Keeping it here means CLI and GUI produce identical reports.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .detect import DAW_NAMES, ProjectFormat
from .errors import READER_NOT_AVAILABLE, UNSUPPORTED_FORMAT, EngineError
from .inputs import ProjectCandidate
from .inventory.scan import InstalledPlugin
from .kb import KnowledgeBase
from .readers import reader_for
from .report import ReportOptions, build_report

# Fixed stage order for progress UIs (SPEC-03 section 8). The report builder runs
# resolve/inventory_match/enrich/media/build as one step, so callers see ``build``.
STAGES = ("detect", "read", "resolve", "inventory_match", "enrich", "media", "build")

StageCallback = Callable[[str], None]


def scan_candidate(
    candidate: ProjectCandidate,
    inventory: list[InstalledPlugin] | None,
    inventory_scanned_at: str | None,
    kb: KnowledgeBase | None,
    options: ReportOptions,
    on_stage: StageCallback | None = None,
) -> dict[str, Any]:
    """Read one project and build its report. ``on_stage`` may raise to cancel."""
    notify = on_stage or (lambda _stage: None)
    det = candidate.detection
    entry: dict[str, Any] = {"detection": candidate.to_dict()}
    if det.format == ProjectFormat.UNSUPPORTED:
        entry.update(
            EngineError(
                UNSUPPORTED_FORMAT, "We can't read this file type yet.", {"reason": det.reason}
            ).to_dict()
        )
        return entry
    reader = reader_for(det.format)
    if reader is None:
        daw = DAW_NAMES.get(det.format, det.format.value)
        entry.update(
            EngineError(
                READER_NOT_AVAILABLE,
                f"{daw} projects are recognised but can't be read in this version yet.",
                {"format": det.format.value},
            ).to_dict()
        )
        return entry
    try:
        notify("read")
        scan = reader.read(Path(det.path))
        notify("build")
        entry["report"] = build_report(
            scan,
            det.to_dict(),
            inventory=inventory,
            inventory_scanned_at=inventory_scanned_at,
            kb=kb,
            options=options,
        )
    except EngineError as exc:
        entry.update(exc.to_dict())
    return entry
