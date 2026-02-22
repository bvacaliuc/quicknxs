# -*- coding: utf-8 -*-
"""Backward-compatible version interface for quicknxs.

The authoritative version is derived from git tags by versioningit
and written to quicknxs/_version.py at install/build time.

Tag convention for quicknxsv1:
  v1.x.y  — major version is always 1
  Bump minor for new features:   git tag v1.3.0 && git push origin v1.3.0
  Bump patch for bug-fixes:      git tag v1.2.1 && git push origin v1.2.1

Between tags the version is:   1.<minor+1>.0.dev<N>  (N = commits since last tag)
At a tag the version is:        1.x.y
"""
import re

try:
    from ._version import __version__
except ImportError:
    __version__ = "1.0.0.dev0"

# Backward-compatible version tuple (major, minor, patch) — e.g. (1, 2, 0)
_m = re.match(r"(\d+)\.(\d+)\.(\d+)", __version__)
version = tuple(int(g) for g in _m.groups()) if _m else (1, 0, 0)

# Backward-compatible version string — PEP 440, e.g. "1.2.0.dev111"
str_version = __version__
