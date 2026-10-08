"""Read the session roster from the shell and detect sessions entering `waiting`."""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import CFG

SCOPE = re.compile(CFG["session_pattern"])
CWD_PREFIXES = tuple(CFG.get("cwd_prefixes") or ())   # checkouts whose sessions count whatever they are named
HEADLESS = re.compile(r"^drift-pr-")   # the Overseer's own `claude -p` drift reviews (drift.py): tools, not peers


def in_scope(a):
    name, cwd = a.get("name") or "", a.get("cwd") or ""
    if not name or HEADLESS.match(name):
        return False
    return bool(SCOPE.match(name)) or any(cwd.startswith(p) for p in CWD_PREFIXES)


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def filter_roster(agents):
    # a session caught mid-start or mid-exit can lack `status`; keep it as unknown rather than crash the watcher
    out = [{"name": a["name"], "status": a.get("status") or "unknown", "kind": a.get("kind"),
            "started_at": _iso(a["startedAt"]) if a.get("startedAt") else None, "cwd": a.get("cwd")}
           for a in agents if in_scope(a)]
    # names can collide (the suffix is two hex digits); the oldest keeps the name, later ones get ~2, ~3 ...
    out.sort(key=lambda a: (a["name"], a["started_at"] or ""))
    seen = {}
    for a in out:
        n = seen.get(a["name"], 0) + 1
        seen[a["name"]] = n
        if n > 1:
            a["name"] = f"{a['name']}~{n}"
    return sorted(out, key=lambda a: a["name"])


def read_roster():
    out = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "claude agents failed")
    return filter_roster(json.loads(out.stdout))


def newly_waiting(prev, cur):
    before = {a["name"]: a["status"] for a in (prev or [])}
    return sorted(a["name"] for a in cur if a["status"] == "waiting" and before.get(a["name"]) != "waiting")


def notify(title, text):
    safe = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e", f'display notification "{safe(text)}" with title "{safe(title)}"'],
                   capture_output=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "roster.json"))
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    prev = json.loads(out.read_text())["sessions"] if out.exists() else None
    cur = read_roster()
    text = json.dumps({"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sessions": cur}, indent=1) + "\n"
    tmp = out.with_name(f".{out.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, out)
    new = newly_waiting(prev, cur)
    for name in new:
        print(name)
        if a.notify:
            notify("Overseer", f"{name} is waiting on you")
    return 0


if __name__ == "__main__":
    sys.exit(main())
