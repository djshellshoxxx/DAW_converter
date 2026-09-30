"""Command line interface: ``rackcheck scan <path> [--json]`` (SPEC-01 section 3).

The CLI calls the same engine functions the GUI will, so fixture regression tests can
drive it directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import ENGINE_VERSION
from .detect import DAW_NAMES, ProjectFormat
from .errors import NO_PROJECT_FOUND, READER_NOT_AVAILABLE, UNSUPPORTED_FORMAT, EngineError
from .inputs import ProjectCandidate, resolve
from .readers import reader_for

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _scan_candidate(candidate: ProjectCandidate) -> dict[str, Any]:
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
        entry["result"] = reader.read(Path(det.path)).to_dict()
    except EngineError as exc:
        entry.update(exc.to_dict())
    return entry


def cmd_detect(args: argparse.Namespace) -> int:
    try:
        with resolve(args.path) as resolved:
            out = [c.to_dict() for c in resolved.candidates]
    except EngineError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        with resolve(args.path) as resolved:
            if not resolved.candidates:
                raise EngineError(
                    NO_PROJECT_FOUND, "No project files found here.", {"path": args.path}
                )
            results = [_scan_candidate(c) for c in resolved.candidates]
    except EngineError as exc:
        if args.json:
            print(json.dumps(exc.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
        return EXIT_ERROR

    failed = any("error" in r for r in results)
    if args.json:
        print(json.dumps({"engine_version": ENGINE_VERSION, "scans": results},
                         indent=2, ensure_ascii=False))
    else:
        for r in results:
            det = r["detection"]
            print(f"{det['path']}")
            print(f"  format: {det['format']} ({det['confidence']}): {det['reason']}")
            if "error" in r:
                print(f"  error: {r['error']['message']}")
            else:
                res = r["result"]
                print(f"  tracks: {len(res['tracks'])}  plugins: {len(res['plugins'])}")
                for p in res["plugins"]:
                    print(f"    - {p['name']} ({p['vendor']}) [{p['format']}, {p['confidence']}]")
    return EXIT_ERROR if failed else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rackcheck", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"rackcheck {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a project file, folder or zip")
    p_scan.add_argument("path")
    p_scan.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    p_scan.set_defaults(func=cmd_scan)

    p_detect = sub.add_parser("detect", help="Only detect project formats (JSON output)")
    p_detect.add_argument("path")
    p_detect.set_defaults(func=cmd_detect)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
