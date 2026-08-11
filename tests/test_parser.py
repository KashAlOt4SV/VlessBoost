from __future__ import annotations

"""Быстрая проверка парсера VLESS без сети."""

from app.vless_parser import endpoint_to_singbox_outbound, parse_vless_url


def test_reality() -> None:
    url = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?encryption=none&flow=xtls-rprx-vision&security=reality"
        "&sni=www.cloudflare.com&fp=chrome&pbk=PUBLICKEY&sid=abcd1234"
        "&type=tcp#MyServer"
    )
    ep = parse_vless_url(url)
    assert ep.server == "example.com"
    assert ep.port == 443
    assert ep.flow == "xtls-rprx-vision"
    assert ep.security == "reality"
    assert ep.public_key == "PUBLICKEY"
    assert ep.name == "MyServer"
    out = endpoint_to_singbox_outbound(ep)
    assert out["type"] == "vless"
    assert out["tls"]["reality"]["enabled"] is True
    print("reality: OK")


def test_ws_tls() -> None:
    url = (
        "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@1.2.3.4:8443"
        "?type=ws&security=tls&path=%2Fvpn&host=cdn.example.com"
        "&sni=cdn.example.com&fp=chrome#ws"
    )
    ep = parse_vless_url(url)
    out = endpoint_to_singbox_outbound(ep)
    assert out["transport"]["type"] == "ws"
    assert out["transport"]["path"] == "/vpn"
    assert out["tls"]["enabled"] is True
    print("ws-tls: OK")


if __name__ == "__main__":
    test_reality()
    test_ws_tls()
    print("all passed")
