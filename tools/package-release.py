"""Package a built Windows folder; never include user profiles or local logs."""
from pathlib import Path
import hashlib
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import __version__

source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist/VEIL"
assets = ROOT / "release-assets"
assets.mkdir(exist_ok=True)
required = [source / path for path in ("VEIL.exe", "_internal", "bin/sing-box.exe", "bin/amneziawg/amneziawg.exe")]
if not all(path.exists() for path in required):
    raise SystemExit("Incomplete runtime folder")
archive = assets / f"VEIL-{__version__}-windows-x64.zip"
allowed_roots = {"VEIL.exe", "_internal", "bin", "THIRD-PARTY-NOTICES.txt", "licenses"}
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative.parts[0] not in allowed_roots:
            continue
        if path.name.lower() in {"settings.json", "app.log", "sing-box.json"} or path.name.lower().endswith((".conf", ".conf.dpapi", ".log")):
            raise SystemExit(f"Unexpected private runtime data: {relative}")
        zip_file.write(path, str(Path("VEIL") / relative))
    zip_file.writestr("VEIL/INSTALL-RU.txt", (
        f"VEIL {__version__} / Windows x64\n\n"
        "Распакуйте всю папку VEIL. Папки _internal и bin должны оставаться рядом с VEIL.exe.\n"
        "Завершите предыдущую версию через трей > Выход, затем запустите VEIL.exe.\n"
        "В настройках импортируйте профиль AmneziaWG 3.1 .conf и выберите нужные приложения.\n"
        "VLESS-ссылка не подходит. Профиль и сервер в архив не включены.\n"
        "Для сетевых адаптеров Windows запросит права администратора.\n"
    ).encode("utf-8"))
with zipfile.ZipFile(archive) as zip_file:
    failure = zip_file.testzip()
    if failure:
        raise SystemExit(f"Damaged ZIP member: {failure}")
digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
(assets / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
print(f"{archive.name}: {archive.stat().st_size} bytes; SHA256 {digest}")
