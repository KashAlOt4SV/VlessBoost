"""User-scoped DPAPI at rest for imported VPN credentials on Windows."""
import base64
import ctypes
import sys


def _crypt(data: bytes, decrypt=False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "VEIL profile", None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)


def seal(text):
    if not text or sys.platform != "win32":
        return text
    return "dpapi:v1:" + base64.b64encode(_crypt(text.encode("utf-8"))).decode("ascii")


def unseal(text):
    if not text.startswith("dpapi:v1:"):
        return text
    return _crypt(base64.b64decode(text[9:]), decrypt=True).decode("utf-8")
