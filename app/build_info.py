"""Packaged build identity loaded from a PyInstaller-bundled JSON resource."""
from __future__ import annotations

import json
from functools import lru_cache

from app import config, version


@lru_cache(maxsize=1)
def get_build_info() -> dict:
    path = config.RESOURCE_ROOT / "build_info.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "version": str(data.get("version") or "unknown"),
                "commit": str(data.get("commit") or "unknown"),
                "built_at": data.get("built_at"),
                "dirty": bool(data.get("dirty", False)),
            }
        except (OSError, ValueError, TypeError):
            pass
    return {"version": version.VERSION, "commit": "unpackaged", "built_at": None, "dirty": True}


def display_text() -> str:
    info = get_build_info()
    commit = info["commit"][:12]
    dirty = " + tracked changes" if info["dirty"] else ""
    built = f" · built {info['built_at']}" if info["built_at"] else ""
    return f"Version {info['version']} · commit {commit}{dirty}{built}"
