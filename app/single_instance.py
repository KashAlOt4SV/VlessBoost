"""Windows single-instance guard (named mutex)."""

from __future__ import annotations

import sys


MUTEX_NAME = "Local\\VLESSBoost_SingleInstance_Mutex"


def ensure_single_instance() -> bool:
    """Return True if this process may continue. False = another instance is running."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ERROR_ALREADY_EXISTS = 183
        # Keep handle alive for process lifetime (GC-safe via module global)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        last = int(kernel32.GetLastError())
        globals()["_mutex_handle"] = handle
        if last == ERROR_ALREADY_EXISTS:
            return False
        return True
    except Exception:
        return True


def notify_already_running() -> None:
    if sys.platform != "win32":
        print("VLESS Boost is already running", file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            "VLESS Boost уже запущен.\nЗакройте текущее окно или откройте его из трея.",
            "VLESS Boost",
            0x00000040,  # MB_ICONINFORMATION
        )
    except Exception:
        pass
