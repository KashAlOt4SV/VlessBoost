from __future__ import annotations

import tempfile
from pathlib import Path

from app import updater as u
from app.updater import _write_apply_bat


def test_apply_bat_has_no_findstr() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        u.UPDATES_DIR = tmp
        u.PENDING_PATH = tmp / "pending.json"
        src = tmp / "src.exe"
        dst = tmp / "dst.exe"
        src.write_bytes(b"x" * 16)
        bat = _write_apply_bat(src=src, dst=dst, wait_pid=12345)
        text = bat.read_text(encoding="utf-8").lower()
        assert "findstr" not in text
        assert "tasklist" not in text
        assert "goto wait" in text
        assert "create_no_window" not in text
        print("apply-bat: OK")


if __name__ == "__main__":
    test_apply_bat_has_no_findstr()
    print("all passed")
