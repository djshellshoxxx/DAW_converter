"""Shared scan path used by both the CLI and the GUI bridge (SPEC-03 section 7).

``scan_candidate`` turns one detected project into either a full report or a stable
error entry. Keeping it here means CLI and GUI produce identical reports.
"""

from __future__ import annotations

import multiprocessing
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .detect import DAW_NAMES, ProjectFormat
from .errors import (
    CORRUPT_PROJECT,
    READER_NOT_AVAILABLE,
    READER_TIMEOUT,
    UNSUPPORTED_FORMAT,
    EngineError,
)
from .inputs import ProjectCandidate
from .inventory.scan import InstalledPlugin
from .kb import KnowledgeBase
from .model import ScanResult
from .readers import reader_for
from .report import ReportOptions, build_report

# Fixed stage order for progress UIs (SPEC-03 section 8). The report builder runs
# resolve/inventory_match/enrich/media/build as one step, so callers see ``build``.
STAGES = ("detect", "read", "resolve", "inventory_match", "enrich", "media", "build")
_READER_TIMEOUT_SECONDS = 60.0
_MAX_READER_RESULT_BYTES = 64 * 1024 * 1024
_WORKER_REAP_SECONDS = 1.0

StageCallback = Callable[[str], None]


def _reader_worker(reader: Any, path: str, connection: Any) -> None:
    """Run one reader in a child process and return only bounded serialized data."""
    try:
        result = reader.read(Path(path))
        message = ("result", result)
    except EngineError as exc:
        message = ("engine_error", exc.code, exc.message, exc.details)
    except BaseException:
        # Do not send tracebacks or exception objects across the process boundary.
        message = ("reader_error",)

    try:
        payload = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
        if len(payload) > _MAX_READER_RESULT_BYTES:
            payload = pickle.dumps(("result_too_large",), protocol=pickle.HIGHEST_PROTOCOL)
        connection.send_bytes(payload)
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        connection.close()


def _stop_reader_worker(process: multiprocessing.Process) -> None:
    """Stop and reap a worker, escalating to kill if it ignores terminate."""
    if process.is_alive():
        process.terminate()
        process.join(_WORKER_REAP_SECONDS)
    if process.is_alive():
        process.kill()
        process.join()


def _read_with_timeout(
    reader: Any, path: Path, timeout_seconds: float = _READER_TIMEOUT_SECONDS
) -> ScanResult:
    """Read a project in a killable process with a bounded result payload."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_reader_worker,
        args=(reader, str(path), send_connection),
        name="rackcheck-reader",
    )
    try:
        process.start()
    except Exception as exc:
        receive_connection.close()
        send_connection.close()
        raise EngineError(
            CORRUPT_PROJECT,
            "Could not start the isolated project reader.",
            {"path": str(path)},
        ) from exc
    send_connection.close()

    try:
        if not receive_connection.poll(timeout_seconds):
            _stop_reader_worker(process)
            raise EngineError(
                READER_TIMEOUT,
                "Reading this project exceeded the time limit.",
                {"path": str(path), "timeout_seconds": timeout_seconds},
            )

        try:
            payload = receive_connection.recv_bytes(_MAX_READER_RESULT_BYTES)
            message = pickle.loads(payload)
        except (EOFError, OSError, pickle.PickleError, ValueError, TypeError):
            raise EngineError(
                CORRUPT_PROJECT,
                "The isolated project reader returned invalid data.",
                {"path": str(path)},
            ) from None

        if not isinstance(message, tuple) or not message:
            raise EngineError(
                CORRUPT_PROJECT,
                "The isolated project reader returned invalid data.",
                {"path": str(path)},
            )
        if message[0] == "result" and len(message) == 2 and isinstance(message[1], ScanResult):
            return message[1]
        if message[0] == "engine_error" and len(message) == 4:
            code, error_message, details = message[1:]
            if (
                isinstance(code, str)
                and isinstance(error_message, str)
                and isinstance(details, dict)
            ):
                raise EngineError(code, error_message, details)
        if message[0] == "result_too_large":
            raise EngineError(
                CORRUPT_PROJECT,
                "The project reader returned too much data.",
                {"path": str(path), "limit_bytes": _MAX_READER_RESULT_BYTES},
            )
        raise EngineError(
            CORRUPT_PROJECT,
            "Could not read this project file.",
            {"path": str(path)},
        )
    finally:
        receive_connection.close()
        _stop_reader_worker(process)


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
        scan = _read_with_timeout(reader, Path(det.path))
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
