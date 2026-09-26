#!/usr/bin/env python
"""Ask this container's own application whether it is ready to serve.

Used as the Docker healthcheck (see compose.yml). It deliberately goes through
HTTP rather than importing the app, so it exercises the same path a request
does, and it belongs in the image rather than in a compose one-liner so it can
be run by hand when something is wrong:

    docker compose exec web python healthcheck.py

The request is addressed to localhost but carries the configured SITE_DOMAIN as
its Host header, because Django would reject 127.0.0.1 as a host name in
production.
"""

import os
import sys
import urllib.error
import urllib.request

PORT = os.environ.get("TC_PORT", "9000")
TIMEOUT = float(os.environ.get("TC_HEALTHCHECK_TIMEOUT", "5"))
HOST_HEADER = os.environ.get("SITE_DOMAIN") or "localhost"


def main():
    url = f"http://127.0.0.1:{PORT}/healthz"
    request = urllib.request.Request(url, headers={"Host": HOST_HEADER})

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        # A 503 is a real answer: the app is up but a dependency is not. Say
        # which, because that is the whole point of the check.
        print(f"unhealthy: /healthz returned {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"unhealthy: cannot reach {url} ({exc})", file=sys.stderr)
        return 1

    if status != 200:
        print(f"unhealthy: /healthz returned {status}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
