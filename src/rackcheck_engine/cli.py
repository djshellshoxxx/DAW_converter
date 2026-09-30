"""Command line interface: ``rackcheck scan <path> [--json]`` (SPEC-01 section 3).

The CLI calls the same engine functions the GUI will, so fixture regression tests can
drive it directly.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from . import ENGINE_VERSION
from .detect import DAW_NAMES, ProjectFormat
from .errors import (
    INVENTORY_UNREADABLE,
    NO_PROJECT_FOUND,
    READER_NOT_AVAILABLE,
    UNSUPPORTED_FORMAT,
    EngineError,
)
from .export import write_csv, write_plugin_list
from .inputs import ProjectCandidate, resolve
from .inventory.scan import InstalledPlugin, load_inventory, scan_installed
from .kb import KnowledgeBase
from .readers import reader_for
from .report import ReportOptions, build_report, plugin_group_key, redact_report

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _scan_candidate(
    candidate: ProjectCandidate,
    inventory: list[InstalledPlugin] | None,
    inventory_scanned_at: str | None,
    kb: KnowledgeBase | None,
    options: ReportOptions,
) -> dict[str, Any]:
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
        scan = reader.read(Path(det.path))
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


def _load_inventory(args: argparse.Namespace) -> tuple[list[InstalledPlugin] | None, str | None]:
    """Returns (inventory, scanned_at); inventory is None when the check is skipped."""
    if args.no_inventory:
        return None, None
    if args.inventory:
        p = Path(args.inventory)
        try:
            if not p.is_file():
                raise OSError("file not found")
            plugins = load_inventory(p)
            stamp = datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(
                timespec="seconds")
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            raise EngineError(
                INVENTORY_UNREADABLE,
                "The saved plugin inventory couldn't be read.",
                {"path": str(p), "reason": str(exc)},
            ) from exc
        return plugins, stamp
    plugins = scan_installed()
    return plugins, datetime.now().astimezone().isoformat(timespec="seconds")


def _indexed(path: str, i: int, total: int) -> str:
    if total <= 1:
        return path
    p = Path(path)
    return str(p.with_name(f"{p.stem}_{i}{p.suffix}"))


def _verdict_text(report: dict[str, Any]) -> list[str]:
    s = report["summary"]
    src = report["source"]
    lines = [
        f"{report['project']['name']}  -  {src['daw_name'] or src['format']}"
        + (f" {src['daw_version']}" if src["daw_version"] else ""),
        f"  Send-ready: {s['send_ready']['score'].upper()}"
        + (f" ({'; '.join(s['send_ready']['reasons'])})" if s["send_ready"]["reasons"] else ""),
    ]
    tc = ", ".join(f"{n} {k}" for k, n in s["track_counts"].items() if n)
    lines.append(f"  Tracks: {tc or 'none found'}")
    lines.append(
        f"  Plugins: {s['unique_plugins']} unique, {s['plugin_instances']} instances, "
        f"{s['missing_plugins']} missing, {s['stock_devices']} built-in devices"
    )
    lines.append(
        f"  Media: {s['media_files']} files, {s['missing_media']} missing, "
        f"{s['media_outside_folder']} outside the project folder"
    )
    if report["warnings"]:
        lines.append("  Warnings:")
        for w in report["warnings"]:
            lines.append(f"    [{w['severity']}] {w['code']}: {w['message']}")
    if report["plugin_summary"]:
        lines.append("  Plugins used:")
        by_key: dict[str, dict[str, Any]] = {}
        for p in report["plugins"]:
            by_key.setdefault(plugin_group_key(p), p)
        for ps in report["plugin_summary"]:
            p = by_key.get(ps["key"], {})
            hp = (p.get("links") or {}).get("homepage") or {}
            link = f"  {hp['url']} ({hp['source']})" if hp.get("url") else ""
            lines.append(
                f"    - {ps['name']} ({ps['vendor'] or 'unknown vendor'}) x{ps['instances']} "
                f"[{ps['resolution_state']}]{link}"
            )
    return lines


def cmd_scan(args: argparse.Namespace) -> int:
    options = ReportOptions(redact_paths=args.redact_paths)
    try:
        inventory, scanned_at = _load_inventory(args)
        kb = KnowledgeBase.load(args.kb)
        with resolve(args.path) as resolved:
            if not resolved.candidates:
                raise EngineError(
                    NO_PROJECT_FOUND, "No project files found here.", {"path": args.path}
                )
            results = [
                _scan_candidate(c, inventory, scanned_at, kb, options)
                for c in resolved.candidates
            ]
    except EngineError as exc:
        if args.json:
            print(json.dumps(exc.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Error: {exc.message}", file=sys.stderr)
        return EXIT_ERROR

    failed = any("error" in r for r in results)
    reports = [r["report"] for r in results if "report" in r]
    try:
        for i, rep in enumerate(reports, start=1):
            if args.csv:
                out = write_csv(rep, _indexed(args.csv, i, len(reports)),
                                redact_paths=args.redact_paths)
                print(f"Wrote {out}", file=sys.stderr)
            if args.plugin_list:
                out = write_plugin_list(rep, _indexed(args.plugin_list, i, len(reports)),
                                        redact_paths=args.redact_paths)
                print(f"Wrote {out}", file=sys.stderr)
    except OSError as exc:
        print(f"Error: couldn't write the export file: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.redact_paths:
        for r in results:
            if "report" in r:
                r["report"] = redact_report(r["report"])

    if args.json:
        print(json.dumps({"engine_version": ENGINE_VERSION, "scans": results},
                         indent=2, ensure_ascii=False))
    else:
        for r in results:
            det = r["detection"]
            if "error" in r:
                print(f"{det['path']}")
                print(f"  format: {det['format']} ({det['confidence']}): {det['reason']}")
                print(f"  error: {r['error']['message']}")
            else:
                print("\n".join(_verdict_text(r["report"])))
    return EXIT_ERROR if failed else EXIT_OK


def cmd_detect(args: argparse.Namespace) -> int:
    try:
        with resolve(args.path) as resolved:
            out = [c.to_dict() for c in resolved.candidates]
    except EngineError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rackcheck", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"rackcheck {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a project file, folder or zip")
    p_scan.add_argument("path")
    p_scan.add_argument("--json", action="store_true",
                        help="Print the full report as JSON (SPEC-02 10.2)")
    p_scan.add_argument("--csv", metavar="PATH", help="Write the full report CSV (SPEC-02 10.3)")
    p_scan.add_argument("--plugin-list", metavar="PATH",
                        help="Write the one-row-per-plugin CSV (SPEC-02 10.4)")
    p_scan.add_argument("--inventory", metavar="PATH",
                        help="Use a saved plugin inventory JSON instead of scanning this machine")
    p_scan.add_argument("--no-inventory", action="store_true",
                        help="Don't check installed plugins (install status shows unknown)")
    p_scan.add_argument("--kb", metavar="DIR", help="Knowledge base folder (default: bundled)")
    p_scan.add_argument("--redact-paths", action="store_true",
                        help="Replace the home folder with ~ and drop outside paths")
    p_scan.set_defaults(func=cmd_scan)

    p_detect = sub.add_parser("detect", help="Only detect project formats (JSON output)")
    p_detect.add_argument("path")
    p_detect.set_defaults(func=cmd_detect)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
