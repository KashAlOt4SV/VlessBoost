from pathlib import Path
import re


def redact(text):
    text = re.sub(r"\b[A-Za-z0-9+/]{43}=", "[ключ скрыт]", str(text))
    return re.sub(r"(?:vpn|vless)://\S+", "[профиль скрыт]", text)


def trim_log_file(path: Path | None = None, *, max_bytes=1_500_000, keep_lines=2500):
    from app.paths import LOG_PATH
    target = path or LOG_PATH
    try:
        if target.exists() and target.stat().st_size > max_bytes:
            # Bounded read even after an unusually long session.
            with target.open("rb") as stream:
                stream.seek(max(0, target.stat().st_size-max_bytes))
                lines = stream.read().decode("utf-8", errors="replace").splitlines()
            target.write_text("\n".join(lines[-keep_lines:])+"\n", encoding="utf-8")
    except OSError:
        pass
