"""Build a native multi-resolution ICO from VEIL's vector-drawn bolt."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from app.ui.veil import bolt_icon

app = QApplication([])
icon = bolt_icon()
images = []
for size in (16, 32, 48, 256):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    icon.pixmap(size, size).save(buffer, "PNG")
    images.append((size, bytes(buffer.data())))
offset = 6 + 16*len(images)
entries = []
for size, data in images:
    entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
target = ROOT / "app/image/veil.ico"
target.write_bytes(struct.pack("<HHH", 0, 1, len(images))+b"".join(entries)+b"".join(data for _, data in images))
print(target)
