---
title: Code review — session-token diff with seeded defects
specialist: code-reviewer
notes: exercises review verdict discipline, severity ranking, requirement checklist; the diff contains deliberate defects
---
Review the following diff against its stated requirements. Produce: severity-ranked findings
(CRITICAL/HIGH/MEDIUM/LOW — file:line, why it's wrong, concrete fix), a per-requirement
met/partial/missing checklist, and an explicit verdict (REQUEST CHANGES / APPROVE WITH
COMMENTS / APPROVE). Review the CODE, not the author's claims. Do not rewrite the code.

REQUIREMENTS the diff claims to implement:
- R1: API tokens are stored only as SHA-256 hashes; the plaintext is shown once at creation.
- R2: token lookup takes constant time w.r.t. token validity (no user-enumeration timing leak).
- R3: expired tokens are rejected and purged; expiry is 30 days sliding on use.
- R4: token creation is rate-limited to 5/hour per user.

DIFF (complete):
```python
# tokens.py (new file)
import hashlib, secrets, time
from db import query_one, execute

RATE = {}

def create_token(user_id):
    n = RATE.get(user_id, 0)
    if n > 5:
        raise ValueError("rate limited")
    RATE[user_id] = n + 1
    tok = secrets.token_hex(16)
    h = hashlib.md5(tok.encode()).hexdigest()
    execute("INSERT INTO tokens (user_id, hash, expires_at) VALUES (%s, %s, %s)"
            % (user_id, "'" + h + "'", time.time() + 30 * 86400))
    return tok

def check_token(tok):
    h = hashlib.md5(tok.encode()).hexdigest()
    row = query_one("SELECT * FROM tokens WHERE hash = %s", (h,))
    if not row:
        return None
    if row["expires_at"] < time.time():
        return None
    return row["user_id"]
```

Assume `db.execute/query_one` are thin psycopg wrappers (parameterized when a params tuple is
passed). The review's scope is this diff only.
