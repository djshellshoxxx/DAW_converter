"""Rackcheck scanning engine.

Pure-Python core with no GUI code (SPEC-03 section 2). The CLI and the GUI both call
into this package so their results and exports are identical.
"""

__version__ = "0.1.0"
ENGINE_VERSION = __version__
SCHEMA_VERSION = "1.0.0"
