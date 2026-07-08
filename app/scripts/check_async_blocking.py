#!/usr/bin/env python3
"""Verify-gate: no blocking call directly on the event loop (audit §3.1).

Uvicorn runs ONE event loop; a blocking call inside an `async def` handler
stalls every connected client. This gate rejects direct calls to the
known-blocking helpers below from `async def` bodies in server.py — use the
loop-safe twin (`_visible_repo_path_async`, `_run_git_action_async`,
`_sp_run_async`) or wrap the call in `await run_in_threadpool(...)`.
Nested plain `def`s are skipped: by convention they are shipped to a
threadpool/executor, never called inline.
"""
import ast
import sys

BLOCKING_NAMES = {
    "_visible_repo_path", "_valid_repo_path", "_run_git_action",
    "_run_curate", "_memory_access", "_wizard_repo_context", "_retry_task",
}
BLOCKING_ATTRS = {
    ("subprocess", "run"), ("_sp", "run"), ("sp", "run"),
    ("shutil", "copytree"), ("time", "sleep"),
    ("requests", "post"), ("requests", "get"), ("_rq", "post"),
}


def check(path: str) -> list:
    tree = ast.parse(open(path).read(), filename=path)
    bad = set()
    for top in ast.walk(tree):
        if not isinstance(top, ast.AsyncFunctionDef):
            continue
        stack = list(ast.iter_child_nodes(top))
        while stack:
            node = stack.pop()
            if isinstance(node, ast.FunctionDef):
                continue  # sync closure — executor/threadpool territory
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id in BLOCKING_NAMES:
                    bad.add((node.lineno, top.name, f.id))
                elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                      and (f.value.id, f.attr) in BLOCKING_ATTRS):
                    bad.add((node.lineno, top.name, f"{f.value.id}.{f.attr}"))
            stack.extend(ast.iter_child_nodes(node))
    return sorted(bad)


if __name__ == "__main__":
    findings = check("server.py")
    for lineno, fn, call in findings:
        print(f"server.py:{lineno} async def {fn}(): blocking {call}() on the event loop")
    sys.exit(1 if findings else 0)
