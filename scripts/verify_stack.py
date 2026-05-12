"""Cross-platform smoke test: hit Go API directly and via nginx /api proxy."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def get(url: str, timeout: float = 15.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main() -> int:
    checks = (
        ("go-api", "http://localhost:18080/health"),
        ("ts-ui /api proxy", "http://localhost:13000/api/health"),
    )
    for name, url in checks:
        print(f"GET {url}")
        try:
            status, body = get(url)
        except OSError as e:
            print(f"  -> FAIL ({e})", file=sys.stderr)
            return 1
        print(f"  -> {status} {body[:200]!r}")
        if status < 200 or status >= 300:
            print(f"  -> FAIL: HTTP {status}", file=sys.stderr)
            return 1
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            print("  -> FAIL: not JSON", file=sys.stderr)
            return 1
        if data.get("redis") != "ok" or data.get("postgres") != "ok":
            print(f"  -> FAIL: degraded payload {data}", file=sys.stderr)
            return 1
    print("verify-stack: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
