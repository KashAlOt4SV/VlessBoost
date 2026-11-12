import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.awg_profile import parse_awg_profile
from app.amneziawg import AmneziaWGManager
from app.config_builder import build_singbox_config
from app.settings import Settings, save_settings, load_settings

KEY = base64.b64encode(bytes(range(32))).decode()
PROFILE = f"""[Interface]
PrivateKey = {KEY}
Address = 10.8.0.2/32
DNS = 1.1.1.1
HeaderProtectionKey = {KEY}
S1 = 12
S2 = 14
S3 = 16
S4 = 18
ContentPaddingAddition = 0-64
RandomTrailers = true
DisableCookies = true
[Peer]
PublicKey = {KEY}
Endpoint = vpn.example.com:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25-35
"""


class ProfileTests(unittest.TestCase):
    def test_preserves_awg3_fields_and_removes_global_dns_routes(self):
        profile = parse_awg_profile(PROFILE)
        self.assertEqual(profile.ipv4, "10.8.0.2")
        output = profile.service_config()
        self.assertIn("headerprotectionkey = " + KEY, output)
        self.assertIn("persistentkeepalive = 25-35", output)
        self.assertIn("Table = off", output)
        self.assertNotIn("dns =", output)
        self.assertIn("contentpaddingaddition = 0-64", output)

    def test_rejects_command_injection_without_echoing_keys(self):
        with self.assertRaisesRegex(ValueError, "команды") as error:
            parse_awg_profile(PROFILE.replace("DNS = 1.1.1.1", "PostUp = malicious.exe"))
        self.assertNotIn(KEY, str(error.exception))
        with self.assertRaisesRegex(ValueError, "Многострочные"):
            parse_awg_profile(PROFILE.replace("RandomTrailers = true", "RandomTrailers = true\n  PostUp = injected.exe"))

    def test_rejects_old_profile_and_invalid_crypto_padding(self):
        for text in (PROFILE.replace("HeaderProtectionKey = " + KEY, ""),
                     PROFILE.replace("S4 = 18", "S4 = 8"), PROFILE.replace(KEY, "secret-invalid-key")):
            with self.assertRaises(ValueError) as error:
                parse_awg_profile(text)
            self.assertNotIn("secret-invalid-key", str(error.exception))

    def test_qcompress_vpn_link(self):
        raw = json.dumps({"containers": [{"awg": {"last_config": PROFILE}}]}).encode()
        encoded = base64.urlsafe_b64encode(len(raw).to_bytes(4, "big") + zlib.compress(raw)).decode().rstrip("=")
        self.assertEqual(parse_awg_profile("vpn://" + encoded).host, "vpn.example.com")

    def test_vless_is_not_silently_reused(self):
        with self.assertRaisesRegex(ValueError, "VLESS"):
            parse_awg_profile("vless://old-profile")

    def test_native_split_outbound_is_bound_and_default_remains_direct(self):
        config = build_singbox_config(Settings(enabled={"discord": True}), proxy_outbound={
            "type": "direct", "tag": "proxy", "bind_interface": "VEIL-AWG",
            "inet4_bind_address": "10.8.0.2",
        }, server_host="vpn.example.com")
        self.assertEqual(config["route"]["final"], "direct")
        self.assertEqual(config["outbounds"][0]["bind_interface"], "VEIL-AWG")
        self.assertTrue(any(rule.get("process_name") and rule["outbound"] == "proxy" for rule in config["route"]["rules"]))
        self.assertTrue(any(rule.get("ip_is_private") and rule["outbound"] == "direct" for rule in config["route"]["rules"]))

    def test_profile_is_encrypted_at_rest_and_atomic_roundtrip(self):
        import sys
        if sys.platform != "win32":
            self.skipTest("Windows DPAPI")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"settings.json"
            with patch("app.settings.SETTINGS_PATH", path):
                save_settings(Settings(awg_config=PROFILE))
                stored = path.read_text(encoding="utf-8")
                self.assertNotIn(KEY, stored)
                self.assertIn("dpapi:v1:", stored)
                self.assertEqual(load_settings().awg_config, PROFILE)
                self.assertFalse(path.with_suffix(".tmp").exists())


class LifecycleTests(unittest.TestCase):
    def test_address_readiness_wait_checks_the_expected_usable_addresses(self):
        from app.amneziawg import wait_for_tunnel_addresses
        with patch("app.amneziawg.powershell") as shell:
            wait_for_tunnel_addresses(["10.8.0.2", "fd00::2"])
        script = shell.call_args.args[0]
        self.assertIn("'10.8.0.2','fd00::2'", script)
        self.assertIn("AddressState -eq 'Preferred'", script)
        self.assertIn("AWG adapter address readiness timeout", script)

    def test_generated_awg_router_config_passes_real_core_validation(self):
        import subprocess
        from app.paths import SINGBOX_EXE
        if not SINGBOX_EXE.exists():
            self.skipTest("Local sing-box binary not installed")
        manager = AmneziaWGManager()
        manager.router = MagicMock()
        manager.router.running = False
        def shell(script, *args):
            if "ProductVersion" in script:
                return "3.1.0"
            if "Get-NetRoute" in script:
                return json.dumps({"InterfaceAlias": "Ethernet", "InterfaceIndex": 4, "NextHop": "192.168.1.1"})
            return ""
        with tempfile.TemporaryDirectory() as directory:
            def validate(settings, **kwargs):
                path = Path(directory)/"router.json"
                path.write_text(json.dumps(kwargs["config"]), encoding="utf-8")
                result = subprocess.run([str(SINGBOX_EXE), "check", "-c", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(KEY, path.read_text())
                self.assertIn("fdfe:dcba:9876::1/126", path.read_text())
                self.assertEqual(kwargs["config"]["inbounds"][0]["route_exclude_address"], ["203.0.113.9/32"])
            manager.router.start.side_effect = validate
            with patch("app.amneziawg.PROFILE_PATH", Path(directory)/"profile.conf.dpapi"), \
                 patch("app.amneziawg.is_admin", return_value=True), \
                 patch("app.amneziawg.find_binary", return_value=Path("amneziawg.exe")), \
                 patch("app.amneziawg.resolve_endpoint", return_value=["203.0.113.9"]), \
                 patch("app.amneziawg.powershell", side_effect=shell), \
                 patch("app.amneziawg.protect_bytes", return_value=b"encrypted"), \
                 patch("app.amneziawg.command", return_value=""), \
                 patch("app.amneziawg.service_state", side_effect=[0, 4, 0, 0]), \
                 patch("app.amneziawg.check_https_proxy", side_effect=RuntimeError("offline probe")):
                with self.assertRaisesRegex(RuntimeError, "offline probe"):
                    manager.start(Settings(awg_config=PROFILE))
            manager.router.start.assert_called_once()

    def test_address_readiness_failure_stops_before_router_start(self):
        manager = AmneziaWGManager()
        manager.router = MagicMock()
        manager.router.running = False
        def shell(script, *args, **kwargs):
            if "ProductVersion" in script:
                return "3.1.0"
            if "Get-NetRoute" in script:
                return json.dumps({"InterfaceAlias": "Ethernet", "InterfaceIndex": 4, "NextHop": "192.168.1.1"})
            if "address readiness timeout" in script:
                raise RuntimeError("address readiness timeout")
            return ""
        with tempfile.TemporaryDirectory() as directory, \
             patch("app.amneziawg.PROFILE_PATH", Path(directory)/"profile.conf.dpapi"), \
             patch("app.amneziawg.is_admin", return_value=True), \
             patch("app.amneziawg.find_binary", return_value=Path("amneziawg.exe")), \
             patch("app.amneziawg.resolve_endpoint", return_value=["203.0.113.9"]), \
             patch("app.amneziawg.powershell", side_effect=shell), \
             patch("app.amneziawg.protect_bytes", return_value=b"encrypted"), \
             patch("app.amneziawg.command", return_value=""), \
             patch("app.amneziawg.service_state", side_effect=[0, 4, 0, 0]):
            with self.assertRaisesRegex(RuntimeError, "address readiness timeout"):
                manager.start(Settings(awg_config=PROFILE))
        manager.router.start.assert_not_called()
        manager.router.stop.assert_called_once()

    def test_failed_native_start_rolls_back_only_owned_service(self):
        manager = AmneziaWGManager()
        manager.router = MagicMock()
        manager.router.running = False
        calls = []
        def shell(script, *args):
            if "ProductVersion" in script:
                return "3.1.0"
            if "Get-NetRoute" in script:
                return json.dumps({"InterfaceAlias": "Ethernet", "InterfaceIndex": 4, "NextHop": "192.168.1.1"})
            raise RuntimeError("adapter failed")
        with tempfile.TemporaryDirectory() as directory, \
             patch("app.amneziawg.PROFILE_PATH", Path(directory)/"test.conf.dpapi"), \
             patch("app.amneziawg.is_admin", return_value=True), \
             patch("app.amneziawg.find_binary", return_value=Path("amneziawg.exe")), \
             patch("app.amneziawg.resolve_endpoint", return_value=["203.0.113.9"]), \
             patch("app.amneziawg.powershell", side_effect=shell), \
             patch("app.amneziawg.protect_bytes", return_value=b"encrypted"), \
             patch("app.amneziawg.command", side_effect=lambda args, *a: calls.append(args)), \
             patch("app.amneziawg.service_state", side_effect=[0, 4, 0, 0]):
            with self.assertRaisesRegex(RuntimeError, "adapter failed"):
                manager.start(Settings(awg_config=PROFILE))
        manager.router.stop.assert_called_once()
        self.assertFalse(manager._owned)
        self.assertTrue(any("/uninstalltunnelservice" in args for args in calls))
        self.assertFalse(any("taskkill" in str(args) for args in calls))

    def test_stop_without_ownership_does_not_touch_other_services(self):
        manager = AmneziaWGManager()
        manager.router = MagicMock()
        with patch("app.amneziawg.service_state") as query:
            manager.stop()
            query.assert_not_called()
        manager.router.stop.assert_called_once()
