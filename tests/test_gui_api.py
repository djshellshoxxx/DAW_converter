"""GUI bridge tests: call the js_api methods directly, no window (SPEC-03 sections 7-8)."""

from __future__ import annotations

import json
import os
import threading
import time
import zipfile
from pathlib import Path

import pytest

from conftest import write_zip
from rackcheck_engine.errors import EXPORT_FAILED, NO_PROJECT_FOUND, UNSUPPORTED_FORMAT
from rackcheck_engine.export import write_csv, write_json
from rackcheck_engine.model import PluginFormat
from rackcheck_gui import api as api_mod
from rackcheck_gui.api import Api

RPP = (
    '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
    "  TEMPO 120 4 4\n"
    "  <TRACK\n"
    '    NAME "Lead"\n'
    "    <FXCHAIN\n"
    '      <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" '
    "12345{A1B2C3D4E5F60718293A4B5C6D7E8F90}\n"
    "        AAAA\n"
    "      >\n"
    "    >\n"
    "  >\n"
    ">\n"
)


class FakeDialogs:
    def __init__(self):
        self.files: list[str] | None = None
        self.folder: str | None = None
        self.save_to: str | None = None
        self.save_calls: list[dict] = []

    def open_files(self):
        return self.files

    def open_folder(self):
        return [self.folder] if self.folder else None

    def save(self, filename, directory, ext):
        self.save_calls.append({"filename": filename, "directory": directory, "ext": ext})
        return self.save_to


class Rig:
    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.events: list[tuple[str, dict]] = []
        self.dialogs = FakeDialogs()
        self.opened: list[str] = []
        self.revealed: list[str] = []
        self.vst3_dir = tmp_path / "plugins"
        self.vst3_dir.mkdir()
        self.api = Api(
            tmp_path / "data",
            emit=lambda n, p: self.events.append((n, p)),
            dialogs=self.dialogs,
            opener=self.opened.append,
            revealer=self.revealed.append,
            plugin_dirs=lambda: {PluginFormat.VST3: [self.vst3_dir]},
        )

    def project(self, name="song.rpp", text=RPP) -> str:
        p = self.tmp / "proj" / name
        p.parent.mkdir(exist_ok=True)
        p.write_text(text, encoding="utf-8")
        self.api._grant(p)
        return str(p)

    def scan(self, path: str, **options):
        r = self.api.start_scan(path, options or None)
        assert "job_id" in r, r
        job = self.api._wait(r["job_id"])
        return job

    def names(self) -> list[str]:
        return [n for n, _ in self.events]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_app_info_lists_readable_and_unreadable_daws(rig):
    info = rig.api.get_app_info()
    assert info["engine_version"] and info["schema_version"]
    by_name = {f["daw_name"]: f for f in info["supported_formats"]}
    assert by_name["REAPER"]["readable"] is True
    assert by_name["Pro Tools"]["readable"] is False and by_name["Pro Tools"]["hint"]
    assert by_name["Bitwig Studio"]["hint"]


def test_only_spec_methods_are_public(rig):
    public = {n for n in dir(rig.api) if not n.startswith("_") and callable(getattr(rig.api, n))}
    spec = {
        "get_app_info", "detect", "start_scan", "cancel_job", "get_report", "export_report",
        "open_report_file", "list_recent", "start_inventory_scan", "get_inventory",
        "get_settings", "set_settings", "update_kb", "open_url", "reveal_path",
        "create_support_bundle",
    }
    extras = {"choose_files", "choose_folder", "choose_export_path", "choose_bundle_path",
              "clear_recent", "get_plugin_folders", "get_log_folder"}
    assert public == spec | extras


def test_ungranted_path_is_refused(rig, tmp_path):
    p = tmp_path / "x.rpp"
    p.write_text(RPP)
    r = rig.api.start_scan(str(p))
    assert r["error"]["code"] == "PATH_NOT_ALLOWED"
    assert rig.api.detect([str(p)])[0]["error"]["code"] == "PATH_NOT_ALLOWED"
    assert rig.api.start_scan(123)["error"]["code"] == "INVALID_ARGUMENT"


def test_scan_emits_progress_then_done_and_report_is_retrievable(rig):
    job = rig.scan(rig.project())
    assert job.state == "done"
    names = rig.names()
    assert names[-1] == "job.done" and "job.progress" in names
    progress = [p for n, p in rig.events if n == "job.progress"]
    assert progress[0]["stage"] == "detect"
    keys = {"job_id", "stage", "stage_index", "stage_count", "percent", "message"}
    assert keys <= set(progress[0])
    assert [p["stage_index"] for p in progress] == sorted(p["stage_index"] for p in progress)
    done = rig.events[-1][1]
    got = rig.api.get_report(done["report_id"])
    assert got["report"]["project"]["name"] == "song"
    assert got["imported"] is False and got["stale"] is False
    assert any(k.startswith("xfer") or k for k in got["plugin_keys"].values())
    # a job id resolves to its report too
    assert rig.api.get_report(job.id)["report_id"] == done["report_id"]
    recent = rig.api.list_recent()
    assert recent[0]["report_id"] == done["report_id"] and recent[0]["project_name"] == "song"


def test_report_matches_cli_engine_path(rig):
    """The bridge uses the same engine function as the CLI (service.scan_candidate)."""
    from rackcheck_engine.cli import _scan_candidate as cli_fn
    from rackcheck_engine.service import scan_candidate

    assert cli_fn is scan_candidate


def test_stale_flag_when_project_changes(rig):
    path = rig.project()
    rid = rig.scan(path).result["report_id"]
    st = Path(path).stat()
    os.utime(path, (st.st_atime, st.st_mtime + 60))
    assert rig.api.get_report(rid)["stale"] is True


def test_inventory_scan_then_report_uses_it(rig):
    (rig.vst3_dir / "Serum.vst3").mkdir()
    r = rig.api.start_inventory_scan(None)
    job = rig.api._wait(r["job_id"])
    assert job.state == "done" and job.result["count"] >= 1
    assert "inventory.updated" in rig.names()
    inv = rig.api.get_inventory()
    assert inv["scanned_at"] and any(p["name"] == "Serum" for p in inv["plugins"])
    rep = rig.api.get_report(rig.scan(rig.project()).result["report_id"])["report"]
    assert rep["machine"]["inventory_scanned_at"] == inv["scanned_at"]
    assert all(p["resolution"]["state"] != "inventory_unavailable" for p in rep["plugins"])


def test_scan_without_inventory_reports_unknown_install_state(rig):
    rep = rig.api.get_report(rig.scan(rig.project()).result["report_id"])["report"]
    assert rep["machine"]["inventory_scanned_at"] is None
    assert rep["plugins"][0]["resolution"]["state"] == "inventory_unavailable"


def test_inventory_folder_failure_does_not_fail_job(rig, monkeypatch):
    (rig.vst3_dir / "A.vst3").mkdir()
    calls = {"n": 0}
    real = api_mod.scan_installed

    def flaky(dirs, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("probe crashed")
        return real(dirs, **kw)

    monkeypatch.setattr(api_mod, "scan_installed", flaky)
    (rig.tmp / "extra").mkdir()
    rig.api._grant(rig.tmp / "extra")
    job = rig.api._wait(rig.api.start_inventory_scan([str(rig.vst3_dir)])["job_id"])
    assert job.state == "done" and job.result["folders_failed"] >= 1


def test_cancel_running_scan(rig, monkeypatch):
    gate = threading.Event()
    reached = threading.Event()

    def slow(cand, inv, at, kb, opts, on_stage=None):
        on_stage("read")
        reached.set()
        gate.wait(5)
        on_stage("build")  # cooperative cancel point
        raise AssertionError("should have been cancelled")

    monkeypatch.setattr(api_mod, "scan_candidate", slow)
    r = rig.api.start_scan(rig.project())
    assert reached.wait(5)
    # A second scan while one is running is refused, not queued.
    assert rig.api.start_scan(rig.project("b.rpp"))["error"]["code"] == "BUSY"
    assert rig.api.cancel_job(r["job_id"]) == {"ok": True}
    gate.set()
    job = rig.api._wait(r["job_id"])
    assert job.state == "cancelled"
    assert rig.names()[-1] == "job.cancelled"
    assert rig.api.cancel_job("nope")["error"]["code"] == "JOB_NOT_FOUND"
    assert rig.api.list_recent() == []  # nothing saved for a cancelled scan


def test_unsupported_file_maps_to_failed_job_with_detection(rig):
    p = rig.tmp / "notes.txt"
    p.write_text("hello")
    rig.api._grant(p)
    job = rig.scan(str(p))
    assert job.state == "failed" and job.error["code"] == UNSUPPORTED_FORMAT
    assert job.error["details"]["detection"]["format"] == "unsupported"
    name, payload = rig.events[-1]
    assert name == "job.failed" and payload["error"]["code"] == UNSUPPORTED_FORMAT


def test_missing_path_and_empty_zip_errors(rig):
    gone = rig.tmp / "gone.rpp"
    rig.api._grant(gone)
    assert rig.api.start_scan(str(gone))["error"]["code"] == "PATH_NOT_FOUND"
    z = write_zip(rig.tmp / "empty.zip", {"readme.txt": b"hi"})
    rig.api._grant(z)
    job = rig.scan(str(z))
    assert job.state == "failed" and job.error["code"] == NO_PROJECT_FOUND
    assert job.error["message"] == "No project files found in this zip."


def test_detect_and_multi_project_selection(rig):
    folder = rig.tmp / "many"
    folder.mkdir()
    (folder / "a.rpp").write_text(RPP)
    (folder / "b.rpp").write_text(RPP)
    rig.api._grant(folder)
    found = rig.api.detect([str(folder)])[0]
    rels = sorted(p["rel_path"] for p in found["projects_found"])
    assert rels == ["a.rpp", "b.rpp"] and found["projects_found"][0]["readable"]
    job = rig.scan(str(folder))
    assert job.error["code"] == "MULTIPLE_PROJECTS" and len(job.error["details"]["projects"]) == 2
    job = rig.scan(str(folder), projects=["b.rpp"])
    assert job.state == "done"
    rep = rig.api.get_report(job.result["report_id"])
    assert rep["report"]["project"]["name"] == "b" and rep["rel_path"] == "b.rpp"
    both = rig.scan(str(folder), projects=["a.rpp", "b.rpp"])
    assert len(both.result["report_ids"]) == 2


def test_zip_scan_and_rescan_identity(rig):
    z = write_zip(rig.tmp / "song.zip", {"inside/s.rpp": RPP.encode()})
    rig.api._grant(z)
    found = rig.api.detect([str(z)])[0]
    assert found["projects_found"][0]["from_archive"] == str(z)
    rel = found["projects_found"][0]["rel_path"]
    job = rig.scan(str(z), projects=[rel])
    assert job.state == "done"
    got = rig.api.get_report(job.result["report_id"])
    assert got["source_path"] == str(z) and got["input_path"] == str(z)
    again = rig.scan(got["input_path"], projects=[got["rel_path"]])
    assert again.state == "done"


def test_exports_write_real_files(rig):
    rid = rig.scan(rig.project()).result["report_id"]
    report = rig.api.get_report(rid)["report"]
    for fmt in ("json", "csv_full", "csv_plugins", "csv_missing"):
        dest = rig.tmp / f"out_{fmt}.{'json' if fmt == 'json' else 'csv'}"
        rig.api._grant(dest)
        res = rig.api.export_report(rid, fmt, str(dest), {"redact_paths": False})
        assert res == {"path": str(dest)} and dest.stat().st_size > 0
    # Byte-identical to calling the engine writers directly (the CLI path).
    ref_json = rig.tmp / "ref.json"
    write_json(report, ref_json)
    assert (rig.tmp / "out_json.json").read_bytes() == ref_json.read_bytes()
    ref_csv = rig.tmp / "ref.csv"
    write_csv(report, ref_csv)
    assert (rig.tmp / "out_csv_full.csv").read_bytes() == ref_csv.read_bytes()
    missing = (rig.tmp / "out_csv_missing.csv").read_text(encoding="utf-8-sig")
    assert "Serum" not in missing  # nothing is "not_installed" without an inventory


def test_export_options_settings_and_errors(rig):
    rid = rig.scan(rig.project()).result["report_id"]
    dest = rig.tmp / "r.json"
    assert rig.api.export_report(rid, "json", str(dest))["error"]["code"] == "PATH_NOT_ALLOWED"
    rig.api._grant(dest)
    assert rig.api.export_report(rid, "html", str(dest))["error"]["code"] == "NOT_AVAILABLE"
    assert rig.api.export_report(rid, "xml", str(dest))["error"]["code"] == "INVALID_ARGUMENT"
    assert rig.api.export_report("nope", "json", str(dest))["error"]["code"] == "REPORT_NOT_FOUND"
    assert rig.api.export_report(rid, "csv_full", str(dest), {"csv_delimiter": "|"})["error"][
        "code"] == "INVALID_ARGUMENT"
    bad = rig.tmp / "no_such_dir" / "r.json"
    rig.api._grant(bad)
    assert rig.api.export_report(rid, "json", str(bad))["error"]["code"] == EXPORT_FAILED
    rig.api.set_settings({"csv_delimiter": ";", "redact_paths": True})
    rig.api.export_report(rid, "csv_full", str(dest))
    text = dest.read_text(encoding="utf-8-sig")
    assert ";" in text.splitlines()[0]
    home = str(Path.home())
    assert home not in text


def test_choose_export_path_uses_default_filename_and_grants(rig):
    rid = rig.scan(rig.project()).result["report_id"]
    rig.dialogs.save_to = str(rig.tmp / "chosen.csv")
    r = rig.api.choose_export_path(rid, "csv_plugins")
    assert r == {"path": rig.dialogs.save_to}
    name = rig.dialogs.save_calls[0]["filename"]
    assert name.startswith("song_plugins_") and name.endswith(".csv")
    assert "path" in rig.api.export_report(rid, "csv_plugins", r["path"])
    rig.dialogs.save_to = None
    assert rig.api.choose_export_path(rid, "json") == {"cancelled": True}


def test_open_report_file_round_trip_and_invalid(rig):
    rid = rig.scan(rig.project()).result["report_id"]
    exported = rig.tmp / "shared.json"
    rig.api._grant(exported)
    rig.api.export_report(rid, "json", str(exported))
    opened = rig.api.open_report_file(str(exported))
    got = rig.api.get_report(opened["report_id"])
    assert got["imported"] is True and got["source_path"] is None
    assert got["report"]["project"]["name"] == "song"
    junk = rig.tmp / "junk.json"
    junk.write_text('{"hello": 1}')
    rig.api._grant(junk)
    assert rig.api.open_report_file(str(junk))["error"]["code"] == "REPORT_INVALID"
    junk.write_text("not json")
    assert rig.api.open_report_file(str(junk))["error"]["code"] == "REPORT_INVALID"


def test_recent_reports_survive_restart_and_clear(rig, tmp_path):
    rid = rig.scan(rig.project()).result["report_id"]
    again = Api(tmp_path / "data", plugin_dirs=lambda: {})
    assert again.list_recent()[0]["report_id"] == rid
    assert again.get_report(rid)["report"]["project"]["name"] == "song"
    assert again.clear_recent()["ok"] is True
    assert again.list_recent() == []
    assert again.get_report(rid)["error"]["code"] == "REPORT_NOT_FOUND"


def test_open_url_allows_only_web_links(rig):
    assert rig.api.open_url("https://example.com/x") == {"ok": True}
    assert rig.api.open_url("http://example.com") == {"ok": True}
    for bad in ("javascript:alert(1)", "file:///c:/windows/system32", "ftp://x.y", "https://", "",
                None, 5):
        assert rig.api.open_url(bad)["error"]["code"] == "INVALID_ARGUMENT"
    assert rig.opened == ["https://example.com/x", "http://example.com"]


def test_reveal_path_only_for_known_locations(rig):
    assert rig.api.reveal_path(str(rig.tmp))["error"]["code"] == "PATH_NOT_ALLOWED"
    proj = rig.project()
    assert rig.api.reveal_path(proj) == {"ok": True}
    assert rig.revealed == [proj]
    log_dir = rig.api.get_log_folder()["path"]
    assert rig.api.reveal_path(log_dir) == {"ok": True}
    assert rig.api.reveal_path("C:\\nope\x00")["error"]["code"] == "INVALID_ARGUMENT"


def test_settings_defaults_persist_and_validate(rig, tmp_path):
    s = rig.api.get_settings()
    assert s["first_run_done"] is False and s["csv_delimiter"] == ","
    assert s["appearance"] == "system"
    out = rig.api.set_settings({"first_run_done": True, "appearance": "dark"})
    assert out["appearance"] == "dark"
    assert Api(tmp_path / "data").get_settings()["appearance"] == "dark"
    assert rig.api.set_settings({"nope": 1})["error"]["code"] == "INVALID_ARGUMENT"
    assert rig.api.set_settings({"appearance": "neon"})["error"]["code"] == "INVALID_ARGUMENT"
    assert rig.api.set_settings("x")["error"]["code"] == "INVALID_ARGUMENT"
    # A folder JS never obtained from a dialog cannot be added.
    assert rig.api.set_settings({"plugin_folders_extra": [str(tmp_path / "zzz")]})["error"][
        "code"] == "PATH_NOT_ALLOWED"
    rig.dialogs.folder = str(tmp_path / "zzz")
    chosen = rig.api.choose_folder()["paths"]
    assert rig.api.set_settings({"plugin_folders_extra": chosen})["plugin_folders_extra"] == chosen
    folders = rig.api.get_plugin_folders()["folders"]
    assert {f["path"] for f in folders} >= {str(rig.vst3_dir), chosen[0]}


def test_dialog_cancel_and_multi_select_grants(rig):
    assert rig.api.choose_files() == {"cancelled": True}
    p = rig.tmp / "d.rpp"
    p.write_text(RPP)
    rig.dialogs.files = [str(p)]
    assert rig.api.choose_files() == {"paths": [str(p)]}
    assert "job_id" in rig.api.start_scan(str(p))
    rig.api._wait(next(iter(rig.api._jobs)))


def test_support_bundle_has_versions_and_no_project_data(rig):
    rig.scan(rig.project())
    dest = rig.tmp / "bundle.zip"
    rig.api._grant(dest)
    assert rig.api.create_support_bundle(str(dest)) == {"path": str(dest)}
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        versions = json.loads(zf.read("versions.json"))
    assert "engine_version" in versions
    assert not any(n.endswith((".rpp", ".json")) and n != "versions.json" for n in names)


def test_unexpected_exception_maps_to_internal_error_without_traceback(rig, monkeypatch):
    def boom(self):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(Api, "_get_kb", boom)
    r = rig.api.get_app_info()
    assert r["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(r) and "Traceback" not in json.dumps(r)


def test_crash_inside_job_becomes_job_failed(rig, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api_mod, "scan_candidate", boom)
    job = rig.scan(rig.project())
    assert job.state == "failed" and job.error["code"] == "INTERNAL_ERROR"
    assert "kaboom" not in json.dumps(rig.events[-1][1])


def test_update_kb_is_honestly_unavailable(rig):
    assert rig.api.update_kb()["error"]["code"] == "NOT_AVAILABLE"


def test_everything_returned_is_json_serialisable(rig):
    rid = rig.scan(rig.project()).result["report_id"]
    for value in (rig.api.get_app_info(), rig.api.get_report(rid), rig.api.list_recent(),
                  rig.api.get_settings(), rig.api.get_inventory(), rig.api.get_plugin_folders()):
        json.dumps(value)
    time.sleep(0)
