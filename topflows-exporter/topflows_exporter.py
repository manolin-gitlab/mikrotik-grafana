import os
import ssl
import time

import librouteros
from prometheus_client import Gauge, start_http_server

HOST = os.environ["MTK_HOST"]
USER = os.environ["MTK_USER"]
PASSWORD = os.environ["MTK_PASSWORD"]
PORT = int(os.environ.get("MTK_PORT", 8728))
USE_SSL = os.environ.get("MTK_USE_SSL", "false").lower() in ("1", "true", "yes")
SSL_VERIFY = os.environ.get("MTK_SSL_VERIFY", "false").lower() in ("1", "true", "yes")
TOP_N = int(os.environ.get("TOP_N", 20))
INTERVAL = int(os.environ.get("INTERVAL", 15))
API_TIMEOUT = int(os.environ.get("API_TIMEOUT", 10))

bytes_gauge = Gauge(
    "mikrotik_connection_bytes",
    "Bytes acumulados de las conexiones activas hacia cada destino (foto del muestreo)",
    ["dst_address", "protocol"],
)
bps_gauge = Gauge(
    "mikrotik_topflows_bps",
    "Bytes por segundo hacia cada destino durante el ultimo intervalo (top talkers)",
    ["dst_address", "protocol"],
)
conn_gauge = Gauge(
    "mikrotik_active_connections",
    "Conexiones activas rastreadas en el momento del muestreo",
)


def dst_ip(raw):
    """Quita el puerto de '1.2.3.4:443' o '[2800::1]:443' sin truncar IPv6."""
    raw = str(raw)
    if raw.startswith("["):
        return raw[1:].split("]", 1)[0]
    if raw.count(":") == 1:
        return raw.split(":", 1)[0]
    return raw


def connect():
    kwargs = {
        "host": HOST,
        "username": USER,
        "password": PASSWORD,
        "port": PORT,
        "timeout": API_TIMEOUT,
    }
    if USE_SSL:
        ctx = ssl.create_default_context()
        if not SSL_VERIFY:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_wrapper"] = ctx.wrap_socket
    return librouteros.connect(**kwargs)


def poll(api, prev, prev_ts):
    conns = list(api.path("/ip/firewall/connection"))
    now = time.monotonic()
    conn_gauge.set(len(conns))

    snapshot = {}
    deltas = {}
    cur = {}
    for c in conns:
        dst = dst_ip(c.get("dst-address", ""))
        proto = c.get("protocol", "unknown")
        b = int(c.get("orig-bytes", 0)) + int(c.get("repl-bytes", 0))
        key = (dst, proto)
        snapshot[key] = snapshot.get(key, 0) + b

        cid = c.get(".id")
        if cid is not None:
            cur[cid] = b
            before = prev.get(cid)
            # Conexion nueva o contador reiniciado: se cuentan sus bytes completos.
            d = b if before is None or b < before else b - before
            deltas[key] = deltas.get(key, 0) + d

    bytes_gauge.clear()
    top = sorted(snapshot.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    for (dst, proto), b in top:
        bytes_gauge.labels(dst_address=dst, protocol=proto).set(b)

    bps_gauge.clear()
    if prev_ts is not None:
        elapsed = max(now - prev_ts, 1.0)
        top = sorted(deltas.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
        for (dst, proto), d in top:
            bps_gauge.labels(dst_address=dst, protocol=proto).set(d / elapsed)

    return cur, now


def main():
    start_http_server(9436)
    prev, prev_ts = {}, None
    while True:
        api = None
        try:
            api = connect()
            while True:
                prev, prev_ts = poll(api, prev, prev_ts)
                time.sleep(INTERVAL)
        except Exception as exc:
            print(f"error conectando/consultando MikroTik: {exc}, reintento en 10s", flush=True)
            prev, prev_ts = {}, None
            time.sleep(10)
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
