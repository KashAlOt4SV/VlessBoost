import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.settings import Settings
from app.ui.veil import VeilWindow


class NativeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for font in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)

    def setUp(self):
        self.patch = patch.object(VeilWindow, "_initial_checks")
        self.patch.start()
        self.window = VeilWindow(settings=Settings(), manager=MagicMock())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._quit()
        self.window.deleteLater()
        self.app.processEvents()
        self.patch.stop()

    def test_navigation_reuses_all_four_pages(self):
        pages = [self.window.stack.widget(i) for i in range(4)]
        started = time.perf_counter()
        for i in range(80):
            self.window._navigate(i % 4)
            self.app.processEvents()
        duration = time.perf_counter()-started
        self.assertEqual(pages, [self.window.stack.widget(i) for i in range(4)])
        self.assertLess(duration, 3.0, f"80 navigations took {duration:.2f}s")

    def test_minimize_restore_stops_busy_animation(self):
        self.window.hero.set_state(False, True, True)
        self.app.processEvents()
        self.assertTrue(self.window.hero.timer.isActive())
        self.window.showMinimized()
        self.app.processEvents()
        self.assertFalse(self.window.hero.timer.isActive())
        self.window._restore()
        self.app.processEvents()
        self.assertFalse(self.window.isMinimized())
        self.assertTrue(self.window.hero.timer.isActive())

    def test_log_backlog_and_document_are_bounded(self):
        import logging
        for _ in range(3000):
            self.window.bridge.emit(logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None))
        self.assertEqual(len(self.window.bridge.pending), 500)
        for _ in range(15):
            self.window._drain()
        self.assertEqual(len(self.window.bridge.pending), 0)
        self.assertLessEqual(self.window.log_view.document().blockCount(), 1000)

    def test_empty_profile_goes_to_import_without_starting_network(self):
        self.window._connect()
        self.assertEqual(self.window.stack.currentIndex(), 2)
        self.window.manager.start.assert_not_called()

    def test_keyboard_toggle_skips_animation(self):
        toggle = self.window.toggles[0]
        toggle.setChecked(not toggle.isChecked())
        self.assertFalse(toggle.animation.state().value == 2)

    def test_explicit_quit_accepts_native_close_instead_of_hiding_to_tray(self):
        from PySide6.QtGui import QCloseEvent
        self.window._quitting = True
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
