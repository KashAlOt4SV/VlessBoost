from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
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
            "VEIL.NetworkAccelerator.2"
        )
    except Exception:
        pass


_windows_app_id()

from app.paths import CONFIG_DIR, LOG_PATH
from app.single_instance import ensure_single_instance, notify_already_running
from app.ui import run_app


def setup_logging() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from app.ui import trim_log_file

        trim_log_file()
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=2, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    if "--self-check" in sys.argv:
        from app.self_check import run
        index = sys.argv.index("--self-check")
        return run(sys.argv[index + 1])
    if not ensure_single_instance():
        notify_already_running()
        return 0

    setup_logging()
    log = logging.getLogger(__name__)
    log.info("VEIL starting — AmneziaWG 3.1")

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
