"""Docker healthcheck: exit 0 if GET /health succeeds, non-zero otherwise."""

import sys
import urllib.request

try:
    urllib.request.urlopen("http://localhost:8000/health", timeout=3)
except Exception:  # pylint: disable=broad-except
    sys.exit(1)
