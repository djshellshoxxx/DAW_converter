"""Installed plugin inventory scanning (SPEC-02 section 6)."""

from .scan import (
    InstalledPlugin,
    PluginSource,
    default_plugin_dirs,
    load_inventory,
    probe_in_subprocess,
    save_inventory,
    scan_installed,
)

__all__ = [
    "InstalledPlugin",
    "PluginSource",
    "default_plugin_dirs",
    "scan_installed",
    "save_inventory",
    "load_inventory",
    "probe_in_subprocess",
]
