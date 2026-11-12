"""Render the real Qt screens without touching settings, services or the network."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.settings import Settings
from app.ui.veil import VeilWindow

app = QApplication([])
for font in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
with patch.object(VeilWindow, "_initial_checks"):
    window = VeilWindow(settings=Settings(), manager=MagicMock())
window.engine_status.setText("●  ЯДРО ГОТОВО")
window.show()
out = ROOT / "docs" / "previews"
out.mkdir(parents=True, exist_ok=True)
for i, name in enumerate(("home", "routing", "settings", "logs")):
    window._navigate(i)
    app.processEvents()
    window.grab().save(str(out / f"{name}.png"))
window._quit()
print(out)
