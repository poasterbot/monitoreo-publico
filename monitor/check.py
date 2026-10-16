#!/usr/bin/env python3
"""Check every portal in portals.json once and append the result to
data/<id>/<YYYY-MM-DD>.json (one file per portal per day, Argentina time)."""

import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
TIMEOUT = 30
# Only the first bytes are read: enough to know the server is answering,
# without downloading multi-megabyte catalogs every half hour.
READ_BYTES = 64 * 1024
# Cloudflare in front of datos.gob.ar tarpits anything that looks like a bot,
# so present as a regular browser: we want to know what a visitor would see.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

UNVERIFIED = ssl.create_default_context()
UNVERIFIED.check_hostname = False
UNVERIFIED.verify_mode = ssl.CERT_NONE


def describe(exc):
    if isinstance(exc, urllib.error.URLError) and exc.reason is not None:
        exc = exc.reason if isinstance(exc.reason, BaseException) else exc
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, socket.gaierror):
        return "dns"
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    if isinstance(exc, ConnectionResetError):
        return "connection reset"
    if isinstance(exc, ssl.SSLError):
        return f"tls: {getattr(exc, 'reason', None) or exc}"
    if isinstance(exc, http.client.BadStatusLine):
        return "invalid http response"
    return " ".join(f"{type(exc).__name__}: {exc}".split())[:200]


def fetch(url, context=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as res:
            res.read(READ_BYTES)
            status = res.status
    except urllib.error.HTTPError as e:
        status = e.code
    return status, round((time.monotonic() - start) * 1000)


def is_cert_error(exc):
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLCertVerificationError)


def attempt(url):
    result = {}
    start = time.monotonic()
    try:
        status, ms = fetch(url)
    except Exception as exc:
        if not is_cert_error(exc):
            return {"up": False, "status": None,
                    "ms": round((time.monotonic() - start) * 1000), "error": describe(exc)}
        # Many gob.ar servers ship incomplete certificate chains that browsers
        # repair on their own. The portal is reachable, so record the TLS
        # problem but keep checking whether it actually answers.
        result["tls_error"] = describe(exc)
        try:
            status, ms = fetch(url, UNVERIFIED)
        except Exception as exc2:
            return {"up": False, "status": None,
                    "ms": round((time.monotonic() - start) * 1000), "error": describe(exc2), **result}
    up = status < 400
    out = {"up": up, "status": status, "ms": ms}
    if not up:
        out["error"] = f"http {status}"
    return {**out, **result}


def check(portal):
    result = attempt(portal["url"])
    if not result["up"]:
        # One retry to filter out a single dropped connection.
        time.sleep(5)
        result = attempt(portal["url"])
    return result


def append(portal, when, result):
    day = when.date().isoformat()
    path = DATA / portal["id"] / f"{day}.json"
    if path.exists():
        doc = json.loads(path.read_text())
    else:
        doc = {"id": portal["id"], "url": portal["url"], "date": day,
               "timezone": str(TZ), "checks": []}
    doc["checks"].append({"time": when.isoformat(timespec="seconds"), **result})
    path.parent.mkdir(parents=True, exist_ok=True)
    # One check per line keeps the files readable and the git diffs small.
    checks = ",\n    ".join(json.dumps(c, ensure_ascii=False) for c in doc["checks"])
    header = {k: v for k, v in doc.items() if k != "checks"}
    body = json.dumps(header, ensure_ascii=False, indent=2)[:-2]
    path.write_text(f'{body},\n  "checks": [\n    {checks}\n  ]\n}}\n')


def main():
    portals = json.loads((ROOT / "portals.json").read_text())
    when = datetime.now(TZ).replace(microsecond=0)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(check, portals))
    for portal, result in zip(portals, results):
        append(portal, when, result)
        mark = "up  " if result["up"] else "DOWN"
        print(f"{mark} {portal['id']:<45} {result.get('status')} {result['ms']}ms {result.get('error', '')}")


if __name__ == "__main__":
    main()
