#!/usr/bin/env python3
"""Quick responsiveness check for the live nexus server."""
import sys, time
sys.path.insert(0, '.')
from scripts._gate_auth import owner_cookie
import requests

CK = owner_cookie()
print('cookie keys:', list(CK.keys()))
for path, to in [('/api/health', 10), ('/api/agents', 30), ('/api/health/full', 10)]:
    t0 = time.time()
    try:
        r = requests.get('https://127.0.0.1:8777' + path, timeout=to, verify=False, cookies=CK)
        dt = time.time() - t0
        body = r.text[:120] if r.status_code != 200 else f'<{len(r.text)} bytes>'
        print(f'{path:20s} {r.status_code} {dt:5.2f}s {body}')
    except Exception as e:
        print(f'{path:20s} ERR {time.time()-t0:.2f}s {type(e).__name__}: {e}')
