"""Docker healthcheck: exit 0 if GET /health succeeds, non-zero otherwise."""

import sys
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=3):
        pass
except Exception:  # pylint: disable=broad-except
    sys.exit(1)
