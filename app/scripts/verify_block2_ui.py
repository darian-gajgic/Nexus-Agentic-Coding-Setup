#!/usr/bin/env python3
"""Runtime UI verification for Block 2 (docs/SPEC-BLOCK2.md):
review v2 modal (unified/split toggle, gutters, syntax highlight, line
comments), galaxy memory modal (edit/merge/delete, confirm-gated), Create-PR
button. Modals are driven directly (reviewTaskUI / openMemoryNodeModal /
openTaskDetail) against seeded probe data — no LLM, self-cleaning.
Run: .venv/bin/python scripts/verify_block2_ui.py
"""
import asyncio
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright
import urllib3
urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from _gate_auth import playwright_cookies  # noqa: E402
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
P, F = 0, 0
console_errors = []


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  PASS  {name}")
    else:
        F += 1
        print(f"  FAIL  {name}  {extra}")


DIFF_FIXTURE = """\
diff --git a/probe.py b/probe.py
index 0000000..1111111 100644
--- a/probe.py
+++ b/probe.py
@@ -1,3 +1,4 @@
 import sys
-def run():
-    return 1
+def run() -> int:
+    # block2 ui probe
+    return 2
"""


def seed_task(repo_path=None, pr_url=None):
    tid = f"task-b2ui{uuid.uuid4().hex[:8]}"
    ws = ROOT / "workspaces" / tid
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "changes.diff").write_text(DIFF_FIXTURE)
    now = time.time()
    db.execute(
        "INSERT INTO tasks (id, title, description, status, created_at, updated_at, "
        "user_id, workspace_path, repo_path, depends_on, result_summary, dispatch_state, pr_url) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, f"b2ui probe {tid[-4:]}", "ui probe", "done", now, now, "u_owner",
         str(ws), repo_path, json.dumps(["task-block2-never-done"]),
         "probe deliverable", "completed", pr_url))
    return tid, ws


async def main():
    global console_errors
    seeded = []
    tid, ws = seed_task(repo_path=str(ROOT))
    seeded.append((tid, ws))
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                          ignore_https_errors=True)
            await page.context.add_cookies(playwright_cookies(BASE))
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
            await page.goto(BASE, wait_until="networkidle")

            # ── review v2 modal ──
            await page.evaluate("([t]) => reviewTaskUI(t, 'b2ui probe')", [tid])
            await page.wait_for_selector(".review-layout", timeout=5000)
            ok("review modal renders", True)
            nums = await page.locator(".review-pane .dl-num").count()
            ok("line-number gutters present", nums >= 8, f"{nums}")
            hl = await page.locator(".review-pane .diff-line pre span").count()
            ok("syntax-highlight spans present", hl > 0, f"{hl}")
            ok("unified is the default view",
               await page.locator(".review-toggle button.active").inner_text() == "Unified")

            await page.click(".review-toggle button:has-text('Side-by-side')")
            await page.wait_for_selector(".split-row", timeout=4000)
            cells = await page.locator(".split-row").first.locator(".split-cell").count()
            ok("split view renders paired cells", cells == 2, f"{cells}")
            ok("view choice persisted",
               await page.evaluate("() => localStorage.getItem('nexusReviewMode')") == "split")

            # comment from the split view (the ＋ appears on hover)
            line = page.locator(".split-cell.add").first
            await line.hover()
            await line.locator(".dl-cbtn").click(force=True)
            await page.wait_for_selector("#rcInput", timeout=4000)
            await page.fill("#rcInput", "b2ui: name the constant")
            await page.click(".rc-composer .btn-primary")
            await page.wait_for_selector(".rc-comment", timeout=4000)
            ok("line comment saved + rendered inline", True)
            foot = await page.locator("#rvFooterInfo").inner_text()
            ok("footer counts the open comment", "1" in foot, foot)
            ok("retry-with-feedback button appears",
               await page.locator("button:has-text('Retry with this feedback')").count() == 1)
            ok("file list shows the 💬 chip",
               await page.locator(".review-file .chip:has-text('💬')").count() >= 1)
            row = db.query_one("SELECT * FROM review_comments WHERE task_id=?", (tid,))
            ok("comment persisted user-scoped", row and row["user_id"] == "u_owner"
               and row["body"] == "b2ui: name the constant", json.dumps(row or {})[:120])

            page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await page.click(".rc-comment .btn-icon[title='Delete']")
            await page.wait_for_selector(".rc-comment", state="detached", timeout=4000)
            ok("comment delete is confirm-gated and works", True)

            await page.click(".review-toggle button:has-text('Unified')")
            await page.wait_for_selector(".diff-line .dl-num", timeout=4000)
            ok("toggle back to unified", True)
            await page.evaluate("() => closeModal()")

            # ── memory modal (edit/merge/delete affordances, confirm gating) ──
            await page.evaluate(
                "() => openMemoryNodeModal({id: 'b2ui-mem-probe', text: 'b2ui probe memory', "
                "agent: 'hermes', user: 'u_owner', created_at: '2026-07-08T00:00:00'})")
            await page.wait_for_selector("#memEditText", timeout=4000)
            val = await page.input_value("#memEditText")
            ok("memory modal opens with editable text", val == "b2ui probe memory", val)
            for label, sel in [("delete", "button:has-text('🗑 Delete')"),
                               ("merge", "button:has-text('⧉ Merge with…')"),
                               ("save", "button:has-text('💾 Save changes')")]:
                ok(f"memory modal has {label}", await page.locator(sel).count() == 1)
            # confirm-gating: dialogs auto-DISMISS by default → no API call may fire
            mem_calls = []
            await page.route("**/api/memory/**",
                             lambda route: (mem_calls.append(route.request.url), route.abort()))
            await page.click("button:has-text('💾 Save changes')")
            await page.click("button:has-text('🗑 Delete')")
            await page.wait_for_timeout(400)
            ok("declining the confirm blocks save AND delete", mem_calls == [], str(mem_calls))
            await page.unroute("**/api/memory/**")
            await page.evaluate("() => closeModal()")

            # ── Create PR button on repo tasks ──
            await page.evaluate(
                "async ([t]) => { state.tasks = await api('GET','/api/tasks'); openTaskDetail(t); }",
                [tid])
            await page.wait_for_selector("button:has-text('⬆ Create PR')", timeout=4000)
            ok("repo task offers ⬆ Create PR", True)
            await page.evaluate("() => closeModal()")
            tid2, ws2 = seed_task(repo_path=str(ROOT), pr_url="https://github.com/x/y/pull/7")
            seeded.append((tid2, ws2))
            await page.evaluate(
                "async ([t]) => { state.tasks = await api('GET','/api/tasks'); openTaskDetail(t); }",
                [tid2])
            await page.wait_for_selector("a:has-text('↗ View PR')", timeout=4000)
            ok("task with pr_url links ↗ View PR", True)

            real_errors = [e for e in console_errors if "favicon" not in e]
            ok("no console errors", not real_errors, "; ".join(real_errors[:3]))
            await browser.close()
    finally:
        for t, w in seeded:
            db.execute("DELETE FROM review_comments WHERE task_id=?", (t,))
            db.execute("DELETE FROM tasks WHERE id=?", (t,))
            shutil.rmtree(w, ignore_errors=True)

    print(f"\n{'='*46}\n  BLOCK 2 UI: {P} passed, {F} failed\n{'='*46}")
    sys.exit(1 if F else 0)


if __name__ == "__main__":
    asyncio.run(main())
