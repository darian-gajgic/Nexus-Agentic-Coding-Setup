#!/usr/bin/env python3
"""Hermes Guardian — verify our hardening; restore it ONLY after a Hermes update.

Default behaviour is PASSIVE (verify + report, mutate NOTHING). The guardian only
re-asserts our changes when it detects that a Hermes update reverted them — i.e.
the tracked repo's git HEAD moved since the last run (``was_update``). This keeps
it from fighting deliberate / manual / runtime edits every 15 minutes. Force a
restore pass by hand with ``guardian.py --restore``.

When it DOES restore, it is precise and scoped strictly to OUR tracked mods —
nothing outside the manifest / core-mods registry is ever touched:
  - Files we fully AUTHORED (override plugin, scripts, skills, compose, mem0.json):
    restored whole from golden/ (only if MISSING or an update reverted them).
  - A file where we edited only PART of a Hermes-shipped file: re-applied via our
    find/replace patch, preserving upstream content.
  - CONFIG values (e.g. agent.reasoning_effort=xhigh, memory.provider=mem0):
    surgically SET one key at a time (backed up, validated, rolled back on error).
  - Core-source edits (core-mods.json): re-applied via git patch, sentinel-checked.
  - Packages / services / containers: reinstalled / enabled / brought up.
When NOT restoring, every drift is still detected and written to the report as
DRIFT/MISSING — it just isn't silently changed.

Runs via hermes-guardian.timer (boot + every 15 min) — verify-only unless the run
detects an update. Manual:
  guardian.py            verify + report (restores only if an update is detected)
  guardian.py --restore  force a full restore of our mods now
  guardian.py --capture  refresh golden/ after an intentional edit to an authored file
"""
import json, os, sys, subprocess, hashlib, shutil, datetime
from pathlib import Path

G = Path.home() / "hermes-guardian"
MANIFEST, REPORTS, STATE, GOLD = G / "manifest.json", G / "reports", G / "state.json", G / "golden"
PATCHES = G / "patches"          # git patches of our Hermes-core modifications
CORE_MODS = G / "core-mods.json"  # registry of tracked core modifications
CORE_STATE = G / "core-mods-state.json"  # per-mod runtime status + user decisions


def expand(p): return Path(os.path.expanduser(str(p)))
def sha256(p):
    try: return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except Exception: return None
def run(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)


def hermes_commit(repo):
    r = run(["git", "-C", str(expand(repo)), "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def dotget(d, path):
    cur = d
    for k in path.split("."):
        if isinstance(cur, dict) and k in cur: cur = cur[k]
        else: return (False, None)
    return (True, cur)


def _git(repo, *args):
    return run(["git", "-C", str(expand(repo))] + list(args))


def reconcile_core_mods(rec, now, may_restore):
    """Reconcile our tracked modifications to Hermes' own source after an update.

    Each mod is a git patch (patches/<name>.patch) against the Hermes repo, with a
    unique `sentinel` string present only when our change is applied. Per mod:
      - intact            -> our change is still present; nothing to do.
      - cleanly reasserted -> update reverted it and `git apply` re-applies with no
                              conflict; we auto-reassert (ours wins) and NOTIFY.
      - conflict          -> update changed the same lines; we do NOT force — we hold
                              it for a human decision surfaced in nexus.
    Standing user decisions are honored: `standing='accept_upstream'` = hands off;
    a one-shot `decision='keep_ours'` force-applies (3-way) then clears.
    Returns (reasserted_mods, coremods_status) for the report + nexus.
    """
    if not CORE_MODS.exists():
        return [], []
    reg = json.loads(CORE_MODS.read_text())
    state = json.loads(CORE_STATE.read_text()) if CORE_STATE.exists() else {}
    repo = expand(reg.get("repo", "~/.hermes/hermes-agent"))
    reasserted, coremods = [], []
    for mod in reg.get("mods", []):
        name = mod["name"]
        target = repo / mod["file"]
        patch = PATCHES / mod["patch"]
        prev = state.get(name, {})
        standing = prev.get("standing")           # persistent: None | 'accept_upstream'
        decision = prev.get("decision")           # one-shot from UI: None | 'keep_ours'
        try:
            applied = target.exists() and mod["sentinel"] in target.read_text()
        except Exception:
            applied = False

        detail, action, status = "", "none", "OK"
        if decision == "keep_ours":               # UI: force our version, then clear
            if applied:
                status, detail = "OK", "already applied"
            else:
                r = _git(repo, "apply", "--3way", str(patch))
                if r.returncode == 0:
                    status, action, detail = "REASSERTED", "git apply", "kept ours (forced)"
                    reasserted.append(mod)
                else:
                    status, detail = "CONFLICT", "keep-ours could not auto-merge; needs manual fix: " + (r.stderr[-140:])
            standing = None
        elif standing == "accept_upstream":       # user chose upstream; stay hands-off
            status = "OK" if applied else "ACCEPTED_UPSTREAM"
            detail = "our change present" if applied else "you chose upstream for this change"
        elif applied:
            status = "OK"
        elif not may_restore:                      # missing, but no update this run -> report only
            status = "DRIFT"
            detail = "our change is absent; re-applies after the next Hermes update (or run guardian.py --restore)"
        else:                                      # missing + update -> reconcile
            chk = _git(repo, "apply", "--check", str(patch))
            if chk.returncode == 0:
                ap = _git(repo, "apply", str(patch))
                if ap.returncode == 0:
                    status, action, detail = "REASSERTED", "git apply", "cleanly re-applied after update"
                    reasserted.append(mod)
                else:
                    status, detail = "FAIL", ap.stderr[-160:]
            else:
                status = "CONFLICT"
                detail = "Hermes changed these lines — awaiting your decision in nexus"

        rec("coremod", name, status, action, detail)
        coremods.append({
            "name": name, "status": status, "detail": detail,
            "description": mod.get("description", ""),
            "impact_if_dropped": mod.get("impact_if_dropped", ""),
            "file": mod["file"], "patch": mod["patch"],
            "standing": standing, "last_checked": now,
        })
        # persist: keep standing, drop the consumed one-shot decision
        state[name] = {"status": status, "standing": standing, "last_checked": now}
    CORE_STATE.write_text(json.dumps(state, indent=2))
    return reasserted, coremods


def _yscalar(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def _find_leaf(lines, keys):
    """Return (line_index, indent) for the dotted `keys`, tracking nesting by indentation
    so ambiguous leaf names (provider/model/base_url appear many times) resolve correctly."""
    stack = []
    for i, line in enumerate(lines):
        raw = line.rstrip("\n"); st = raw.lstrip(" ")
        if not st or st.startswith("#") or st.startswith("- ") or (":" not in st and not st.endswith(":")):
            continue
        indent = len(raw) - len(st)
        key = st.split(":", 1)[0].strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if [k for _, k in stack] + [key] == keys:
            return i, indent
        stack.append((indent, key))
    return None, None


def surgical_config(config_path, ops):
    """Change ONLY the target line(s) — every other byte is preserved (no reformat/re-indent).
    ops: ('set', dotpath, value) | ('list_add', dotpath, value) | ('list_remove', dotpath, value).
    Backs up, validates the result parses, rolls back on failure. Returns (ok, detail)."""
    import yaml as pyyaml
    p = expand(config_path)
    bak = p.with_name(p.name + ".guardian-bak")
    shutil.copy2(p, bak)
    try:
        for kind, dotpath, value in ops:
            lines = p.read_text().splitlines(keepends=True)
            keys = dotpath.split(".")
            i, indent = _find_leaf(lines, keys)
            if kind == "set":
                if i is None:
                    return False, f"{dotpath} not found"
                lines[i] = " " * indent + f"{keys[-1]}: {_yscalar(value)}\n"
            elif kind == "list_add":
                if i is None:
                    return False, f"{dotpath} list not found"
                item_indent = indent + 2
                for j in range(i + 1, len(lines)):
                    s = lines[j].rstrip("\n"); ss = s.lstrip(" ")
                    if ss.startswith("- "):
                        item_indent = len(s) - len(ss); break
                    if ss and not ss.startswith("#"):
                        break
                lines.insert(i + 1, " " * item_indent + f"- {_yscalar(value)}\n")
            elif kind == "list_remove":
                if i is None:
                    continue
                for j in range(i + 1, len(lines)):
                    s = lines[j].rstrip("\n"); ss = s.lstrip(" ")
                    if ss and not ss.startswith("- ") and not ss.startswith("#") and (len(s) - len(ss)) <= indent:
                        break
                    if ss in (f"- {value}", f"- '{value}'", f'- "{value}"'):
                        del lines[j]; break
            p.write_text("".join(lines))
        pyyaml.safe_load(p.read_text())  # validate
        os.remove(bak)
        return True, "ok"
    except Exception as e:
        shutil.copy2(bak, p)  # rollback
        return False, str(e)[:150]


def capture(m):
    for f in m["files"]:
        src = expand(f["path"])
        if src.exists() and f.get("restore_mode") != "patch":
            shutil.copy2(src, GOLD / f["golden"])
    print("golden/ refreshed (authored files only; patch-file left as-is)")


def main():
    m = json.loads(MANIFEST.read_text())
    if "--capture" in sys.argv:
        return capture(m)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    commit = hermes_commit(m["hermes_repo"])
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    was_update = ("hermes_commit" in prev) and (prev.get("hermes_commit") != commit)
    force_restore = "--restore" in sys.argv
    # Mutate ONLY after a detected Hermes update (git HEAD moved) or an explicit
    # --restore. Otherwise the guardian verifies and reports but changes nothing.
    may_restore = was_update or force_restore
    checks = []
    def rec(kind, item, status, action="none", detail=""):
        checks.append({"kind": kind, "item": item, "status": status, "action": action, "detail": detail})

    # 1. FILES  (restore only on update/--restore; otherwise report drift)
    for f in m["files"]:
        dst, g = expand(f["path"]), GOLD / f["golden"]
        patches = f.get("patches")
        if not dst.exists():
            if not may_restore:
                rec("file", f["path"], "MISSING", "none", "file absent; run guardian.py --restore to recreate")
            else:
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(g, dst)
                    if f.get("mode"): os.chmod(dst, int(f["mode"], 8))
                    rec("file", f["path"], "RESTORED", "copied golden", "was missing")
                except Exception as e:
                    rec("file", f["path"], "FAIL", "restore failed", str(e))
        elif patches:  # partial edit to a Hermes-shipped file: our find/replace
            text = dst.read_text()
            missing = [pt for pt in patches if pt["find"] in text]  # find present == our edit reverted
            if not missing:
                rec("file", f["path"], "OK", "none", "our edit present; upstream content intact")
            elif not may_restore:
                rec("file", f["path"], "DRIFT", "none", f"our edit reverted ({len(missing)}); re-applies after update or --restore")
            else:
                for pt in missing:
                    text = text.replace(pt["find"], pt["replace"])
                dst.write_text(text)
                rec("file", f["path"], "RESTORED", "surgical patch", f"re-applied {len(missing)} edit(s); upstream preserved")
        elif sha256(dst) != sha256(g):
            if may_restore:
                shutil.copy2(g, dst)
                if f.get("mode"): os.chmod(dst, int(f["mode"], 8))
                rec("file", f["path"], "RESTORED", "copied golden", "update reverted it" if was_update else "forced restore")
            else:
                rec("file", f["path"], "DRIFT", "none", "differs from golden (deliberate edit? run --capture)")
        else:
            rec("file", f["path"], "OK")

    # 2. CONFIG — verify; surgically enforce the crucial ones (collect ops, apply once)
    config_ops = []
    try:
        import yaml
        cfg = yaml.safe_load(expand(m["config_file"]).read_text())
        for cv in m["config_values"]:
            ok, val = dotget(cfg, cv["path"])
            if ok and val == cv["expected"]:
                rec("config", cv["path"], "OK")
            elif cv.get("enforce") and may_restore:
                config_ops.append(("set", cv["path"], cv["expected"]))
                rec("config", cv["path"], "RESTORED", "surgical set", f"{val!r} -> {cv['expected']!r}")
            else:
                rec("config", cv["path"], "DRIFT", "none", f"expected {cv['expected']!r}, got {val!r}")
        for cc in m["config_contains"]:
            ok, val = dotget(cfg, cc["path"])
            if ok and isinstance(val, list) and cc["must_include"] in val:
                rec("config", cc["path"], "OK")
            elif cc.get("enforce") and may_restore:
                config_ops.append(("list_add", cc["path"], cc["must_include"]))
                rec("config", cc["path"], "RESTORED", "surgical add", f"added {cc['must_include']!r}")
            else:
                rec("config", cc["path"], "DRIFT", "none", f"missing {cc['must_include']!r}")
        for ca in m["config_absent"]:
            ok, _ = dotget(cfg, ca["path"])
            rec("config", ca["path"] + " (absent)", "OK" if not ok else "DRIFT", "none", "" if not ok else "should be absent")
        dis = (cfg.get("skills") or {}).get("disabled") or []
        for s in m["skills_disabled_must_exclude"]:
            if s not in dis:
                rec("config", f"skills.disabled excludes {s}", "OK")
            elif m.get("skills_disabled_enforce") and may_restore:
                config_ops.append(("list_remove", "skills.disabled", s))
                rec("config", f"skills.disabled excludes {s}", "RESTORED", "surgical remove", f"removed {s}")
            else:
                rec("config", f"skills.disabled excludes {s}", "DRIFT")
    except Exception as e:
        rec("config", m["config_file"], "FAIL", "none", str(e))
    if config_ops:
        okc, info = surgical_config(m["config_file"], config_ops)
        if not okc:
            for c in checks:
                if c["kind"] == "config" and c["status"] == "RESTORED":
                    c["status"], c["detail"] = "FAIL", "surgical edit rolled back: " + info

    # 3. ENV presence (names only)
    try:
        names = {l.split("=", 1)[0] for l in expand(m["env_file"]).read_text().splitlines()
                 if "=" in l and not l.lstrip().startswith("#")}
        for e in m["env_present"]:
            rec("env", e, "OK" if e in names else "MISSING", "none",
                "" if e in names else "secret var missing — re-add manually (cannot auto-restore)")
    except Exception as e:
        rec("env", m["env_file"], "FAIL", "none", str(e))

    # 4. PACKAGES
    py, uv = str(expand(m["hermes_venv_python"])), os.path.expanduser("~/.local/bin/uv")
    for pkg in m["packages"]:
        name = pkg["spec"].split("==")[0]
        want = pkg["spec"].split("==")[1] if "==" in pkg["spec"] else None
        probe = run([py, "-c", f"import importlib.metadata as md, {pkg['import']}; print(md.version('{name}'))"])
        if probe.returncode == 0:
            ver = probe.stdout.strip()
            rec("package", pkg["spec"], "OK" if (not want or ver == want) else "DRIFT", "none",
                "" if (not want or ver == want) else f"installed {ver}")
        elif not may_restore:
            rec("package", pkg["spec"], "MISSING", "none", "not installed; reinstalls after update or --restore")
        else:
            ins = run([uv, "pip", "install", "--python", py, pkg["spec"]])
            rec("package", pkg["spec"], "RESTORED" if ins.returncode == 0 else "FAIL", "uv pip install",
                "was missing" if ins.returncode == 0 else ins.stderr[-200:])

    # 5. SERVICES
    for s in m["services"]:
        base = ["systemctl"] + (["--user"] if s["scope"] == "user" else [])
        en = run(base + ["is-enabled", s["unit"]]).stdout.strip()
        if en == "enabled":
            rec("service", s["unit"], "OK")
        elif not s.get("restorable"):
            rec("service", s["unit"], "OK" if en == "enabled" else "DRIFT", "none", f"is-enabled={en} (not auto-managed)")
        elif not may_restore:
            rec("service", s["unit"], "DRIFT", "none", f"is-enabled={en}; enables after update or --restore")
        elif run(base + ["cat", s["unit"]]).returncode == 0:
            run(base + ["enable", "--now", s["unit"]])
            rec("service", s["unit"], "RESTORED", "enabled", f"was {en}")
        else:
            rec("service", s["unit"], "MISSING", "none", "unit file not installed yet")

    # 6. CONTAINERS
    for c in m.get("containers", []):
        name = c["name"]
        up_now = bool(run(["docker", "ps", "--filter", f"name={name}", "--format", "{{.Names}}"]).stdout.strip())
        ready = True
        if c.get("ready_url"):
            ready = run(["curl", "-s", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}", c["ready_url"]]).stdout.strip() in ("200", "204")
        if up_now and ready:
            rec("container", name, "OK")
        elif not may_restore:
            rec("container", name, "DRIFT", "none", "down/not ready; brought up after update or --restore")
        else:
            r = run(["docker", "compose", "-f", str(expand(c["compose_dir"]) / "docker-compose.yml"), "up", "-d"])
            rec("container", name, "RESTORED" if r.returncode == 0 else "FAIL", "docker compose up -d",
                "was down/not ready" if r.returncode == 0 else r.stderr[-160:])

    # 7. CORE MODIFICATIONS — re-assert our Hermes-source patches (or hold conflicts)
    reasserted_mods, coremods = reconcile_core_mods(rec, now, may_restore)

    # Summary + report
    summary = {}
    for c in checks:
        summary[c["status"]] = summary.get(c["status"], 0) + 1
    restored = [c for c in checks if c["status"] in ("RESTORED", "REASSERTED")]
    problems = [c for c in checks if c["status"] in ("FAIL", "MISSING", "DRIFT", "CONFLICT")]
    conflicts = [c for c in checks if c["status"] == "CONFLICT"]
    # gateway reload when we changed something it loads (config/package/plugin file or a reasserted core mod)
    gw_restarted = False
    gw_affecting = [c for c in restored if c["kind"] in ("package", "config")
                    or any(x in c["item"] for x in ("plugins/", "mem0.json"))]
    gw_affecting += list(reasserted_mods)  # any reasserted core mod is runtime Hermes source
    if gw_affecting:
        gw_restarted = run(["hermes", "gateway", "restart"]).returncode == 0
    report = {
        "timestamp": now, "hermes_commit": commit, "prev_commit": prev.get("hermes_commit"),
        "was_post_update": was_update, "mode": "restore" if may_restore else "verify",
        "forced": force_restore, "summary": summary, "total": len(checks),
        "restored": [f'{c["kind"]}:{c["item"]} ({c["action"]})' for c in restored],
        "gateway_restarted": gw_restarted,
        "problems": [{"item": f'{c["kind"]}:{c["item"]}', "status": c["status"], "detail": c["detail"]} for c in problems],
        "core_mods": coremods,
        "conflicts": [{"item": c["item"], "detail": c["detail"]} for c in conflicts],
        "checks": checks,
        "overall": "CONFLICT" if conflicts else ("RESTORED" if restored else ("PROBLEMS" if problems else "OK")),
    }
    REPORTS.mkdir(exist_ok=True)
    if was_update or restored or problems:
        (REPORTS / f"{now.replace(':', '-')}.json").write_text(json.dumps(report, indent=2))
    (G / "latest-report.json").write_text(json.dumps(report, indent=2))
    STATE.write_text(json.dumps({"hermes_commit": commit, "last_run": now}, indent=2))
    mode = "RESTORE" if may_restore else "verify-only"
    hint = "" if may_restore else "  (drift is reported, not changed — run --restore to force)"
    print(f"guardian [{mode}]: {len(checks)} checks | restored={len(restored)} | problems={len(problems)} | "
          f"conflicts={len(conflicts)} | core_mods={len(coremods)} | post_update={was_update} | overall={report['overall']}{hint}")


if __name__ == "__main__":
    main()
