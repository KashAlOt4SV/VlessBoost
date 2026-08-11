from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _windows_app_id() -> None:
    """Чтобы Windows не группировал окно с python.exe и брал иконку exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            "VLESS.Boost.App.1"
        )
    except Exception:
        pass


_windows_app_id()

from app.paths import CONFIG_DIR, LOG_PATH
from app.ui import run_app


def setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    setup_logging()
    logging.getLogger(__name__).info("VLESS Boost starting")
    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
