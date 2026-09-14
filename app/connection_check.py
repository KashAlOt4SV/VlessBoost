"""HTTPS diagnostic using SOCKS5 remote DNS, bounded by one deadline."""
import socket
import ssl
import time


def read_exact(sock, length, deadline=None):
    result = bytearray()
    while len(result) < length:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Connection check timed out")
            sock.settimeout(remaining)
        data = sock.recv(length-len(result))
        if not data:
            raise ConnectionError('Proxy closed the connection')
        result.extend(data)
    return bytes(result)


def check_https_proxy(port, host, timeout=8.0):
    started = time.monotonic()
    deadline = started + timeout
    def budget(sock):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Connection check timed out')
        sock.settimeout(remaining)
    name = host.encode('idna')
    if not 0 < len(name) <= 255:
        raise ValueError('Invalid hostname')
    with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
        budget(sock)
        sock.sendall(b'\x05\x01\x00')
        if read_exact(sock,2,deadline) != b'\x05\x00':
            raise ConnectionError('Local SOCKS5 proxy is not ready')
        budget(sock)
        sock.sendall(b'\x05\x01\x00\x03'+bytes([len(name)])+name+b'\x01\xbb')
        reply=read_exact(sock,4,deadline)
        if reply[:3] != b'\x05\x00\x00':
            raise ConnectionError(f'SOCKS5 connect failed (code {reply[1]})')
        if reply[3]==1:
            read_exact(sock,6,deadline)
        elif reply[3]==4:
            read_exact(sock,18,deadline)
        elif reply[3]==3:
            read_exact(sock,read_exact(sock,1,deadline)[0]+2,deadline)
        else:
            raise ConnectionError('Invalid SOCKS5 address type')
        budget(sock)
        with ssl.create_default_context().wrap_socket(sock,server_hostname=host) as tls:
            budget(tls)
            tls.sendall(f'HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode('ascii'))
            response=bytearray()
            while b'\r\n' not in response and len(response)<4096:
                budget(tls)
                part=tls.recv(512)
                if not part:
                    break
                response.extend(part)
            status=bytes(response).split(b'\r\n',1)[0].decode('ascii',errors='replace')
            if not status.startswith('HTTP/'):
                raise ConnectionError('No HTTP response through proxy')
    return f'{host}: {status}; HTTPS handshake + response {(time.monotonic()-started)*1000:.0f} ms'
