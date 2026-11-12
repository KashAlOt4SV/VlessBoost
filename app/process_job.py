"""Close only this app's child processes if its Windows process crashes."""
import ctypes
from ctypes import wintypes
import logging
import sys


class ChildJob:
    def __init__(self, process):
        self.handle = None
        if sys.platform != "win32":
            return

        class Basic(ctypes.Structure):
            _fields_ = [("ProcessTime", ctypes.c_longlong), ("JobTime", ctypes.c_longlong),
                        ("Flags", wintypes.DWORD), ("MinimumWorkingSet", ctypes.c_size_t),
                        ("MaximumWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                        ("Scheduling", wintypes.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("IOCounters", ctypes.c_ulonglong * 6),
                        ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
                        ("PeakProcessMemory", ctypes.c_size_t), ("PeakJobMemory", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = self.api.CreateJobObjectW(None, None)
        information = Extended()
        information.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (not handle or not self.api.SetInformationJobObject(handle, 9, ctypes.byref(information), ctypes.sizeof(information))
                or not self.api.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle))):
            code = ctypes.get_last_error()
            if handle:
                self.api.CloseHandle(handle)
            logging.getLogger(__name__).warning("Child job unavailable: Windows error %s", code)
            return
        self.handle = handle

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
