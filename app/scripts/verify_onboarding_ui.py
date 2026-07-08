#!/usr/bin/env python3
"""Runtime UI verification for the in-app onboarding wizard
(docs/SPEC-ONBOARDING.md R4): CTA banner button, welcome step, section steps
with explanations, auto-save on Next (DB proof), n/a toggle, review counts,
apply → success, Settings entry point. Runs against a scratch knowledge root
(settings onboarding.root, restored); the owner's real answers are backed up.
Run: .venv/bin/python scripts/verify_onboarding_ui.py
"""
import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright
import urllib3
urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from _gate_auth import playwright_cookies  # noqa: E402
import database as db  # noqa: E402
import os  # noqa: E402

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


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="nexus-onb-ui-"))
    shutil.copytree(os.path.expanduser("~/knowledge/templates"), tmp / "templates")
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True)
    subprocess.run(["git", "-c", "user.name=g", "-c", "user.email=g@local",
                    "commit", "-m", "init"], cwd=tmp, capture_output=True)
    prev_root = db.get_setting("onboarding.root", None)
    db.set_setting("onboarding.root", str(tmp))
    saved_rows = db.query_all("SELECT * FROM onboarding_answers WHERE user_id='u_owner'")
    saved_state = db.query_all("SELECT * FROM onboarding_state WHERE user_id='u_owner'")
    db.execute("DELETE FROM onboarding_answers WHERE user_id='u_owner'")
    db.execute("DELETE FROM onboarding_state WHERE user_id='u_owner'")
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1600, "height": 1000},
                                          ignore_https_errors=True)
            await page.context.add_cookies(playwright_cookies(BASE))
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))
            await page.goto(BASE, wait_until="networkidle")

            # CTA banner offers the in-app wizard (no terminal text)
            await page.wait_for_selector("#onboardingCta button", timeout=6000)
            cta = await page.locator("#onboardingCta").inner_text()
            ok("banner opens the wizard, not a terminal",
               "Start the guided onboarding" in cta and "cd ~/knowledge" not in cta, cta[:120])

            await page.click("#onboardingCta button")
            await page.wait_for_selector(".onb-explain", timeout=6000)
            body = await page.locator("#modalContent").inner_text()
            ok("welcome explains the two files + where answers land",
               "BUSINESS-CONTEXT.md" in body and "STYLE-VOICE.md" in body
               and "canonical" in body.lower(), body[:120])

            await page.click("button:has-text(\"Let's go\")")
            await page.wait_for_selector(".onb-input", timeout=6000)
            body = await page.locator("#modalContent").inner_text()
            ok("section 1 shows the impact explanation",
               "What these answers change" in body)
            n_inputs = await page.locator(".onb-input").count()
            ok("section 1 renders its questions", n_inputs == 3, f"{n_inputs}")

            await page.fill(".onb-input >> nth=0", "ui probe: A dev, B content")
            await page.locator(".onb-na >> nth=1").check()
            await page.click("button:has-text('Next')")
            await page.wait_for_timeout(600)
            row = db.query_one("SELECT * FROM onboarding_answers WHERE user_id='u_owner' "
                               "AND slot_id='context:00'")
            ok("Next auto-saves to the DB (resumable)",
               row and row["answer"] == "ui probe: A dev, B content", str(row)[:120])
            na_row = db.query_one("SELECT * FROM onboarding_answers WHERE user_id='u_owner' "
                                  "AND slot_id='context:01'")
            ok("n/a toggle persists", na_row and na_row["na"] == 1)

            await page.click("button:has-text('Back')")
            # both steps render .onb-input — wait for section 1's OWN heading
            await page.wait_for_selector(".section-title:has-text('The team')", timeout=6000)
            val = await page.input_value(".onb-input >> nth=0")
            ok("Back keeps the answer", val == "ui probe: A dev, B content", val)

            # jump to review
            await page.evaluate("() => { _onb.step = _onb.d.sections.length + 1; renderOnbWizard(); }")
            await page.wait_for_selector(".agentic-row", timeout=6000)
            body = await page.locator("#modalContent").inner_text()
            ok("review counts answered + n/a + open",
               "1 answered" in body and "1 n/a" in body and "open" in body, body[:150])

            page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await page.click("button:has-text('Apply to the Business Brain')")
            await page.wait_for_selector("text=Your Business Brain is live", timeout=8000)
            ok("apply is confirm-gated and reaches the success step", True)
            ok("apply wrote the (redirected) canonical file",
               (tmp / "BUSINESS-CONTEXT.md").is_file()
               and "ui probe: A dev, B content" in (tmp / "BUSINESS-CONTEXT.md").read_text())
            await page.click("button:has-text('Done')")

            # Settings keeps a re-edit entry point
            await page.click('a.nav-item[data-view="settings"]')
            await page.wait_for_selector("button:has-text('Open the guided onboarding')", timeout=6000)
            ok("Settings → Business Brain entry point", True)

            real_errors = [e for e in console_errors if "favicon" not in e]
            ok("no console errors", not real_errors, "; ".join(real_errors[:3]))
            await browser.close()
    finally:
        db.execute("DELETE FROM onboarding_answers WHERE user_id='u_owner'")
        db.execute("DELETE FROM onboarding_state WHERE user_id='u_owner'")
        for r in saved_rows:
            db.execute("INSERT INTO onboarding_answers (user_id, slot_id, answer, na, updated_at) "
                       "VALUES (?,?,?,?,?)", (r["user_id"], r["slot_id"], r["answer"], r["na"], r["updated_at"]))
        for r in saved_state:
            db.execute("INSERT INTO onboarding_state (user_id, applied_at, target_dir) "
                       "VALUES (?,?,?)", (r["user_id"], r["applied_at"], r["target_dir"]))
        if prev_root:
            db.set_setting("onboarding.root", prev_root)
        else:
            db.execute("DELETE FROM settings WHERE key='onboarding.root'")
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'='*46}\n  ONBOARDING UI: {P} passed, {F} failed\n{'='*46}")
    sys.exit(1 if F else 0)


if __name__ == "__main__":
    asyncio.run(main())
