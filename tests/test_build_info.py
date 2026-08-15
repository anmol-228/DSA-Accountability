import json

from app import build_info, config


def test_packaged_build_info_is_loaded_and_displayable(tmp_path, monkeypatch):
    payload = {
        "version": "1.2.3",
        "commit": "0123456789abcdef",
        "built_at": "2026-08-15T00:00:00Z",
        "dirty": False,
    }
    (tmp_path / "build_info.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(config, "RESOURCE_ROOT", tmp_path)
    build_info.get_build_info.cache_clear()
    try:
        assert build_info.get_build_info() == payload
        text = build_info.display_text()
        assert "Version 1.2.3" in text
        assert "commit 0123456789ab" in text
    finally:
        build_info.get_build_info.cache_clear()
