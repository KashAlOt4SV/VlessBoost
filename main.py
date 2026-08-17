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
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    if not ensure_single_instance():
        notify_already_running()
        return 0

    setup_logging()
    log = logging.getLogger(__name__)
    log.info("VLESS Boost starting")

    try:
        from app.updater import abort_stuck_apply_scripts, apply_pending_update_on_startup

        abort_stuck_apply_scripts()
        if apply_pending_update_on_startup():
            log.info("Exiting to apply pending OTA update")
            return 0
    except Exception:
        log.exception("pending update check failed")

    run_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
