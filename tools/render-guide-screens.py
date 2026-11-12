"""Capture real Qt controls for the quickstart, using a harmless example profile."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QFrame
from app.settings import Settings
from app.ui.veil import VeilWindow

app = QApplication([])
for name in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
with patch.object(VeilWindow, "_initial_checks"):
    window = VeilWindow(settings=Settings(enabled={"discord": True, "youtube": True}), manager=MagicMock())
window.resize(1000, 760)
window.show()
out = ROOT / "docs/guide"
out.mkdir(exist_ok=True)
window._navigate(2)
app.processEvents()
settings_page = window.stack.widget(2).widget()
profile_card = settings_page.findChildren(QFrame, "card")[0]
profile_card.grab().save(str(out / "settings-import.png"))
window._navigate(1)
app.processEvents()
height = window.table.horizontalHeader().height() + sum(window.table.rowHeight(i) for i in range(5)) + 2
window.table.grab(QRect(0, 0, window.table.width(), height)).save(str(out / "routing-switches.png"))

key = base64.b64encode(bytes(range(32))).decode()
window.settings.awg_config = (
    f"[Interface]\nPrivateKey = {key}\nAddress = 10.8.0.2/32\nHeaderProtectionKey = {key}\n"
    "S1 = 12\nS2 = 12\nS3 = 12\nS4 = 12\n"
    f"[Peer]\nPublicKey = {key}\nEndpoint = 203.0.113.10:51820\nAllowedIPs = 0.0.0.0/0\n"
)
window.settings.profile_name = "Пример профиля"
window._profile_summary()
window._navigate(0)
app.processEvents()
window.hero.grab().save(str(out / "home-connect.png"))
window._quit()
print(out)
