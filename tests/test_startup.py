import socket
import subprocess
import threading
import unittest
from unittest.mock import MagicMock, patch

from app.startup_check import probe_socks, wait_for_proxy


class StartupTests(unittest.TestCase):
    def test_slow_fragmented_greeting_is_accepted(self):
        errors = []
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(3)
            def serve():
                try:
                    with listener.accept()[0] as conn:
                        conn.settimeout(2)
                        conn.recv(3)
                        threading.Event().wait(0.4)
                        conn.sendall(b'\x05')
                        threading.Event().wait(0.05)
                        conn.sendall(b'\x00')
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            try:
                probe_socks(listener.getsockname()[1], timeout=2)
            finally:
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)

    def test_retry_after_timeout(self):
        proc = MagicMock(pid=123)
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired('sing-box', 0.2)
        with patch('app.startup_check.probe_socks', side_effect=[socket.timeout('slow'), None]) as probe:
            wait_for_proxy(proc, 10808)
            self.assertEqual(probe.call_count, 2)

    def test_dead_process_is_not_success(self):
        proc = MagicMock(returncode=2)
        proc.poll.return_value = 2
        with patch('app.startup_check.probe_socks') as probe:
            with self.assertRaisesRegex(RuntimeError, 'код 2'):
                wait_for_proxy(proc, 10808)
            probe.assert_not_called()

    def test_deadline_message_identifies_local_port(self):
        proc = MagicMock(pid=123)
        proc.poll.return_value = None
        with self.assertRaisesRegex(RuntimeError, '127.0.0.1:10808'):
            wait_for_proxy(proc, 10808, timeout=0)

    def test_wrong_protocol_is_rejected(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.return_value = b'HT'
        with patch('app.startup_check.socket.create_connection', return_value=sock):
            with self.assertRaisesRegex(ConnectionError, 'не как SOCKS5'):
                probe_socks(10808)

    def test_closed_socket_is_rejected(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.return_value = b''
        with patch('app.startup_check.socket.create_connection', return_value=sock):
            with self.assertRaises(ConnectionError):
                probe_socks(10808)


class CoreOutputTests(unittest.TestCase):
    def test_final_error_is_drained_and_ansi_removed(self):
        import sys
        from app.startup_check import CoreOutput
        proc = subprocess.Popen([sys.executable, '-c',
            "print('INFO opening TUN'); print('\\x1b[31mFATAL create adapter: access denied\\x1b[0m')"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        output = CoreOutput(proc.stdout)
        output.start()
        proc.wait(timeout=5)
        output.finish()
        self.assertFalse(output.thread.is_alive())
        self.assertEqual(output.summary(), 'FATAL create adapter: access denied')

    def test_output_history_is_bounded(self):
        import io
        from app.startup_check import CoreOutput
        output = CoreOutput(io.StringIO('INFO ready\n' * 500))
        output.start()
        output.finish()
        self.assertEqual(len(output.lines), 30)
