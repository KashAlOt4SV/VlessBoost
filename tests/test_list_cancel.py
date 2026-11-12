import threading
import time
import unittest
from unittest.mock import patch
from app.list_updater import update_all_remote


class ListCancellationTests(unittest.TestCase):
    def test_unresponsive_provider_does_not_hold_shutdown(self):
        cancelled = threading.Event()
        release = threading.Event()
        timer = threading.Timer(.06, cancelled.set)
        timer.daemon = True
        timer.start()
        try:
            with patch("app.list_updater.update_preset_lists", side_effect=lambda _: release.wait(3)):
                started = time.monotonic()
                result = update_all_remote(["discord"], cancel_event=cancelled)
                self.assertLess(time.monotonic()-started, .5)
                self.assertEqual(result, {})
        finally:
            release.set()
            timer.cancel()
