"""Report unresolved imports among packaged DLLs (build-time diagnostic)."""
from pathlib import Path
import pefile
import sys

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist-smoke/VEIL/_internal"
files = list(base.rglob("*.dll")) + list(base.rglob("*.pyd"))
index = {path.name.lower(): path for path in files}
cache = {}
pending = [base / "PySide6/QtCore.pyd", base / "PySide6/Qt6Core.dll"]
seen = set()
while pending:
    path = pending.pop()
    if path in seen:
        continue
    seen.add(path)
    pe = pefile.PE(str(path), fast_load=True, max_symbol_exports=100000)
    pe.parse_data_directories(directories=[1])
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dependency = index.get(entry.dll.decode().lower())
        if dependency is None:
            continue
        if dependency not in cache:
            exports = pefile.PE(str(dependency), fast_load=True, max_symbol_exports=100000)
            exports.parse_data_directories(directories=[0])
            cache[dependency] = {symbol.name for symbol in exports.DIRECTORY_ENTRY_EXPORT.symbols}
        missing = [item.name for item in entry.imports if item.name and item.name not in cache[dependency]]
        if missing:
            print(path.name, "->", dependency, "missing", missing)
        pending.append(dependency)
