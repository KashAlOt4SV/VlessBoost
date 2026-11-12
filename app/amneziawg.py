"""Official AWG Windows service + sing-box process/domain/IP classifier.

The native AWG adapter has no automatic routes or DNS. A high-metric route
allows explicitly interface-bound router sockets; ordinary traffic is pinned
to the original uplink. Only this application's named service is managed.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes
import json
import ipaddress
import logging
import os
import socket
from pathlib import Path
import subprocess
import threading
import time

from app.awg_profile import parse_awg_profile
from app.config_builder import build_singbox_config
from app.connection_check import check_https_proxy
from app.paths import BIN_DIR, CONFIG_DIR
from app.log_utils import redact
from app.singbox import SingBoxManager, is_admin, _create_no_window

log = logging.getLogger(__name__)
TUNNEL = "VEIL-AWG"
SERVICE = "AmneziaWGTunnel$" + TUNNEL
PROFILE_PATH = CONFIG_DIR / (TUNNEL + ".conf.dpapi")


def command(args, timeout=20):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, creationflags=_create_no_window())
    if result.returncode:
        # Do not echo configs, keys, or process arguments into the log.
        raise RuntimeError(f"Ошибка {Path(args[0]).name}, код {result.returncode}: "
                           + redact(result.stderr or result.stdout)[-1500:])
    return result.stdout.strip()


def powershell(script, timeout=20):
    return command(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; "
                    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); "
                    "$OutputEncoding = [Console]::OutputEncoding; " + script], timeout)


def get_uplink(tun_interface):
    # Ignore other VPN default routes when a real gateway is available. Never
    # route AWG's outer packets through our own classifier or another tunnel.
    excluded = [TUNNEL, tun_interface]
    escaped = ",".join("'" + value.replace("'", "''") + "'" for value in excluded)
    result = json.loads(powershell(
        "$adapters=@{}; Get-NetAdapter | ForEach-Object { $adapters[[int]$_.ifIndex]=$_ }; "
        f"$excluded=@({escaped}); "
        "$routes=@(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | "
        "Where-Object { $_.InterfaceAlias -notin $excluded -and $_.NextHop -ne '0.0.0.0' "
        "-and $adapters[[int]$_.InterfaceIndex].Status -eq 'Up' }); "
        "$route=$routes | Sort-Object @{Expression={if($adapters[[int]$_.InterfaceIndex].HardwareInterface){0}else{1}}}, "
        "@{Expression={$_.RouteMetric + $_.InterfaceMetric}} | Select-Object -First 1; "
        "if($null -eq $route){throw 'No active uplink with a gateway'}; "
        "$route | Select-Object InterfaceAlias,InterfaceIndex,NextHop | ConvertTo-Json -Compress"))
    if not result or "\ufffd" in result["InterfaceAlias"]:
        raise RuntimeError("Не удалось прочитать имя исходного сетевого интерфейса")
    return result


def resolve_endpoint(host):
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None, type=socket.SOCK_DGRAM)}
        if not addresses:
            raise RuntimeError("Не удалось разрешить адрес AWG-сервера")
        return sorted(addresses)


def protect_bytes(data: bytes) -> bytes:
    """DPAPI machine scope: the tunnel service runs as LocalSystem."""
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), TUNNEL, None,
                                                None, None, 4, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(output.data)


def find_binary() -> Path:
    candidates = [BIN_DIR / "amneziawg" / "amneziawg.exe",
                  Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "AmneziaWG" / "amneziawg.exe"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Не найден AmneziaWG 3.1. Запустите tools\\prepare-runtime.ps1 или установите официальный AmneziaWG 3.1.")


def service_state() -> int:
    """Query only our service using SCM; 0 means absent."""
    from ctypes import wintypes
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.OpenSCManagerW.restype = wintypes.HANDLE
    api.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    api.OpenServiceW.restype = wintypes.HANDLE
    api.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    api.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    manager = api.OpenSCManagerW(None, None, 1)
    if not manager:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        handle = api.OpenServiceW(manager, SERVICE, 4)
        if not handle:
            code = ctypes.get_last_error()
            if code == 1060:
                return 0
            raise ctypes.WinError(code)
        try:
            status = (wintypes.DWORD * 9)()
            needed = wintypes.DWORD()
            api.QueryServiceStatusEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
            if not api.QueryServiceStatusEx(handle, 0, status, ctypes.sizeof(status), ctypes.byref(needed)):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(status[1])
        finally:
            api.CloseServiceHandle(handle)
    finally:
        api.CloseServiceHandle(manager)


class AmneziaWGManager:
    def __init__(self):
        self.router = SingBoxManager()
        self.active_settings = None
        self._owned = False
        self._lock = threading.RLock()
        self._endpoint_routes = []
        self.cancel_event = threading.Event()

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise RuntimeError("Подключение отменено")

    @property
    def running(self):
        return self._owned and self.router.running

    def _remove_service(self):
        if service_state():
            command([str(find_binary()), "/uninstalltunnelservice", TUNNEL])
            deadline = time.monotonic() + 10
            while service_state() and time.monotonic() < deadline:
                time.sleep(.15)
            if service_state():
                raise RuntimeError("Служба VEIL-AWG ещё останавливается. Повторите отключение.")
        PROFILE_PATH.unlink(missing_ok=True)
        self._owned = False

    def cleanup_stale(self):
        with self._lock:
            if not self._owned and service_state():
                log.warning("Removing stale VEIL-AWG service from previous session")
                self._remove_service()

    def start(self, settings):
        with self._lock:
            self._check_cancelled()
            if self.running:
                return
            if not is_admin():
                raise PermissionError("Для сетевого адаптера нужны права администратора. Запустите VEIL от имени администратора.")
            profile = parse_awg_profile(settings.awg_config)
            executable = find_binary()
            # Never guess capabilities from a file name or accept an older AWG release.
            version = powershell(f"(Get-Item -LiteralPath '{str(executable).replace(chr(39), chr(39)*2)}').VersionInfo.ProductVersion")
            if not version.startswith("3.1."):
                raise RuntimeError("Нужен официальный AmneziaWG версии 3.1.x. Обновите сетевой runtime.")
            self.router.ensure_binary()
            self._check_cancelled()
            self.cleanup_stale()
            uplink = get_uplink(settings.tun_interface)
            if not uplink:
                raise RuntimeError("Не найдено прямое подключение к интернету")
            config = build_singbox_config(settings, proxy_outbound={
                "type": "direct", "tag": "proxy", "bind_interface": TUNNEL,
                "inet4_bind_address": profile.ipv4, "connect_timeout": "8s",
            }, server_host=profile.host)
            config["outbounds"][1]["bind_interface"] = uplink["InterfaceAlias"]
            log.info("Direct uplink selected: %s (index %s)", uplink["InterfaceAlias"], uplink["InterfaceIndex"])
            endpoints = resolve_endpoint(profile.host)
            endpoint_routes = [address + ("/32" if ipaddress.ip_address(address).version == 4 else "/128")
                               for address in endpoints]
            config["inbounds"][0]["route_exclude_address"] = endpoint_routes
            config["route"]["rules"].insert(0, {"ip_cidr": endpoint_routes, "outbound": "direct"})
            config["route"]["rules"].insert(0, {"process_name": ["amneziawg.exe"], "outbound": "direct"})
            # A dedicated local probe always tests AWG, regardless of selected presets.
            config["route"]["rules"].insert(0, {"inbound": ["mixed-in"], "outbound": "proxy"})
            config["inbounds"][0]["mtu"] = int(profile.interface["mtu"])
            # Capture IPv6 as well, so a selected process cannot bypass AWG via
            # an IPv6 literal or a previously cached AAAA record.
            config["inbounds"][0]["address"].append("fdfe:dcba:9876::1/126")
            v6 = [ipaddress.ip_interface(value.strip()) for value in profile.interface["address"].split(",")
                  if ipaddress.ip_interface(value.strip()).version == 6]
            if v6 and any(ipaddress.ip_network(value.strip(), strict=False) == ipaddress.ip_network("::/0")
                          for value in profile.peer["allowedips"].split(",")):
                config["outbounds"][0]["inet6_bind_address"] = str(v6[0].ip)
            else:
                # The TUN still captures IPv6; explicitly refuse selected IPv6
                # instead of letting a socket fall back to the physical uplink.
                rules = []
                for rule in config["route"]["rules"]:
                    if rule.get("outbound") == "proxy":
                        reject = {key: value for key, value in rule.items() if key != "outbound"}
                        reject.update({"ip_version": 6, "action": "reject"})
                        rules.append(reject)
                    rules.append(rule)
                config["route"]["rules"] = rules
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PROFILE_PATH.write_bytes(protect_bytes(profile.service_config().encode("utf-8")))
            # Machine DPAPI also needs a restrictive file ACL, including the parent.
            try:
                command(["icacls.exe", str(PROFILE_PATH), "/inheritance:r", "/grant:r",
                         "*S-1-5-18:F", "*S-1-5-32-544:F"])
                log.info("Starting official AmneziaWG 3.1 transport")
                self._owned = True  # Roll back even if installation partially succeeds.
                command([str(executable), "/installtunnelservice", str(PROFILE_PATH)])
                self._check_cancelled()
                powershell(
                    "$deadline=(Get-Date).AddSeconds(15); do { "
                    "$a=Get-NetAdapter -Name 'VEIL-AWG' -ErrorAction SilentlyContinue; "
                    "if($a.Status -eq 'Up'){break}; Start-Sleep -Milliseconds 150 "
                    "} while((Get-Date) -lt $deadline); "
                    "if($a.Status -ne 'Up'){throw 'AWG adapter readiness timeout'}; "
                    "Set-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 6000; "
                    "New-NetRoute -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
                    "-NextHop '0.0.0.0' -RouteMetric 6000 -PolicyStore ActiveStore | Out-Null")
                if config["outbounds"][0].get("inet6_bind_address"):
                    powershell(
                        "Set-NetIPInterface -InterfaceAlias 'VEIL-AWG' -AddressFamily IPv6 -AutomaticMetric Disabled -InterfaceMetric 6000; "
                        "New-NetRoute -InterfaceAlias 'VEIL-AWG' -AddressFamily IPv6 -DestinationPrefix '::/0' "
                        "-NextHop '::' -RouteMetric 6000 -PolicyStore ActiveStore | Out-Null")
                self._check_cancelled()
                # Preserve an explicit physical route while TUN is active. The
                # native service's own bind cannot override a more specific TUN route.
                for address in endpoints:
                    if ipaddress.ip_address(address).version == 4:
                        route_script = (
                            f"$prefix='{address}/32'; $index={int(uplink['InterfaceIndex'])}; "
                            f"$gateway='{ipaddress.ip_address(uplink['NextHop'])}'; "
                            "$existing=Get-NetRoute -InterfaceIndex $index -DestinationPrefix $prefix -ErrorAction SilentlyContinue; "
                            "if(-not $existing){ New-NetRoute -InterfaceIndex $index -DestinationPrefix $prefix "
                            "-NextHop $gateway -RouteMetric 1 -PolicyStore ActiveStore | Out-Null; 'created' }")
                        if powershell(route_script) == "created":
                            self._endpoint_routes.append((address + "/32", int(uplink["InterfaceIndex"])))
                self.router.start(settings, kill_external=False, config=config)
                # Readiness is an actual HTTPS round trip through AWG, not an open local port.
                check_https_proxy(settings.socks_port, "one.one.one.one", timeout=12)
                self._check_cancelled()
                self.active_settings = deepcopy(settings)
                log.info("AmneziaWG tunnel verified; split routing active")
            except Exception:
                self.stop()
                raise

    def stop(self):
        with self._lock:
            self.router.stop()
            if self._owned:
                self._remove_service()
            for prefix, index in list(self._endpoint_routes):
                powershell(f"Get-NetRoute -DestinationPrefix '{prefix}' -InterfaceIndex {index} "
                           "-ErrorAction SilentlyContinue | Where-Object { $_.RouteMetric -eq 1 } | "
                           "Remove-NetRoute -Confirm:$false -ErrorAction Stop")
                self._endpoint_routes.remove((prefix, index))
            self.active_settings = None
            log.info("VEIL tunnel disconnected")

    def telemetry(self):
        """No private keys: query only transfer and handshake via official awg CLI."""
        executable = find_binary().with_name("awg.exe")
        if not executable.exists():
            return {"rx": None, "tx": None, "handshake": None, "alive": service_state() == 4}
        output = command([str(executable), "show", TUNNEL, "transfer"], timeout=3)
        rx = tx = 0
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 3:
                rx += int(fields[1]); tx += int(fields[2])
        handshakes = command([str(executable), "show", TUNNEL, "latest-handshakes"], timeout=3)
        latest = max((int(line.split()[-1]) for line in handshakes.splitlines() if line.split()), default=0)
        return {"rx": rx, "tx": tx, "handshake": latest, "alive": service_state() == 4}
