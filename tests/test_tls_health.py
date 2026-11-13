"""Exercise missing roots, actual TLS rejection, and independent AWG readiness."""
from pathlib import Path
import socket
import ssl
import threading
import unittest
from unittest.mock import patch

from app.amneziawg import AmneziaWGManager
from app.connection_check import tls_context


class TrustStoreTests(unittest.TestCase):
    def test_missing_system_roots_are_supplemented_without_disabling_tls(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(empty.cert_store_stats()["x509_ca"], 0)
        with patch("app.connection_check.ssl.create_default_context", return_value=empty):
            context = tls_context.__wrapped__()
        self.assertGreater(context.cert_store_stats()["x509_ca"], 100)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def _assert_tls_rejected(self, context, hostname):
        fixture = Path(__file__).parent / "fixtures"
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(fixture/"localhost-test-cert.pem", fixture/"localhost-test-key.pem")
        errors = []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(3)
            def serve():
                try:
                    with listener.accept()[0] as connection:
                        connection.settimeout(3)
                        try:
                            with server.wrap_socket(connection, server_side=True):
                                pass
                        except ssl.SSLError:
                            pass  # The client correctly rejects the certificate.
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            with socket.create_connection(listener.getsockname(), timeout=3) as sock:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    context.wrap_socket(sock, server_hostname=hostname)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)

    def test_untrusted_certificate_is_still_rejected(self):
        self._assert_tls_rejected(tls_context.__wrapped__(), "localhost")

    def test_hostname_mismatch_is_still_rejected(self):
        context = tls_context.__wrapped__()
        # Trust the disposable fixture only in this private test context.
        context.load_verify_locations(cafile=str(Path(__file__).parent/"fixtures/localhost-test-cert.pem"))
        self._assert_tls_rejected(context, "different.example")


class HealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.manager = AmneziaWGManager()
        self.manager._transport_started_at = 990
        self.stats = {"alive": True, "rx": 4096, "tx": 2048, "handshake": 995}
        self.error = ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")

    def test_certificate_failure_retains_only_independently_verified_awg(self):
        with patch("app.amneziawg.time.time", return_value=1000), \
             patch("app.amneziawg.check_https_proxy", side_effect=self.error):
            self.assertIsNone(self.manager.check_health(10808, stats=self.stats))
        self.assertIn("сертификат", self.manager.health_warning)

    def test_unknown_stale_previous_session_or_dead_handshake_is_not_success(self):
        variants = [{"handshake": 0}, {"handshake": 980}, {"handshake": 1100},
                    {"alive": False}, {"rx": 0}, {"rx": None}]
        for change in variants:
            with self.subTest(change=change), \
                 patch("app.amneziawg.time.time", return_value=1000), \
                 patch("app.amneziawg.check_https_proxy", side_effect=self.error):
                with self.assertRaisesRegex(RuntimeError, "handshake"):
                    self.manager.check_health(10808, stats={**self.stats, **change})
        self.manager._transport_started_at = 100
        with patch("app.amneziawg.time.time", return_value=1000):
            self.assertFalse(self.manager.has_fresh_handshake({**self.stats, "handshake": 500}))

    def test_timeout_does_not_become_a_success(self):
        with patch("app.amneziawg.check_https_proxy", side_effect=TimeoutError("timeout")):
            with self.assertRaises(TimeoutError):
                self.manager.check_health(10808, stats=self.stats)

    def test_success_clears_the_certificate_warning(self):
        self.manager.health_warning = "earlier failure"
        with patch("app.amneziawg.check_https_proxy", return_value="HTTP/1.1 200 OK"):
            self.assertIsInstance(self.manager.check_health(10808), int)
        self.assertIsNone(self.manager.health_warning)
