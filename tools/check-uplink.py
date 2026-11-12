"""Exercise a real interface-bound UDP socket through sing-box, without a TUN."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.amneziawg import get_uplink
from app.paths import SINGBOX_EXE

uplink = get_uplink("vless-split")
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as allocation:
    allocation.bind(("127.0.0.1", 0))
    port = allocation.getsockname()[1]
config = {
    "log": {"level": "warn"},
    "inbounds": [{"type": "direct", "listen": "127.0.0.1", "listen_port": port,
                  "network": "udp", "override_address": "1.1.1.1", "override_port": 53}],
    "outbounds": [{"type": "direct", "tag": "direct", "bind_interface": uplink["InterfaceAlias"]}],
    "route": {"final": "direct"},
}
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/"test.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    child = subprocess.Popen([str(SINGBOX_EXE), "run", "-c", str(path)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        time.sleep(.4)
        if child.poll() is not None:
            raise RuntimeError(child.stdout.read().decode("utf-8", errors="replace"))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(4)
            query = b"\x6a\x2c\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
            sock.sendto(query, ("127.0.0.1", port))
            response = sock.recv(4096)
            assert response[:2] == query[:2] and response[2] & 0x80
            print(json.dumps({"udp_dns_reply_bytes": len(response), "uplink": uplink, "ok": True}, ensure_ascii=True))
    finally:
        child.terminate()
        output = child.communicate(timeout=3)[0]
        if output:
            print(output.decode("utf-8", errors="replace"))
