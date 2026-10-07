"""Drift review: when a PR crosses the round cap, a headless `claude -p` reads its review history
and writes a verdict for the human. Read-only by construction: the allowed tools are reads and gh
GETs, and the report goes to stdout, which we redirect to a file. One run per PR head.

State lives in state["drift_runs"][pr] = {pid, path, head, started, done}.
"""
import os
import subprocess
from pathlib import Path

from config import CFG

PROMPT = Path(__file__).with_name("drift-prompt.md")
REPO_DIR = CFG.get("drift_cwd") or None      # a checkout of the repo for git; None inherits the Overseer's cwd
ALLOWED_TOOLS = [
    "Read", "Grep", "Glob",
    "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh pr checks:*)",
    "Bash(gh api:*)",        # GETs; the prompt forbids writes and the run has no other write path
    "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git fetch:*)",
]
VERDICTS = ("CONVERGED", "CONVERGING", "SPIRALLING", "STALLED-ON-HUMAN")


def prompt_for(pr, rounds, cap):
    return PROMPT.read_text().format(pr=pr, rounds=rounds, cap=cap, repo=CFG["repo"],
                                     gating_bot=CFG["gating_bot"], human=CFG["human"])


def _spawn(argv, out_path, cwd):
    """Detached so a tick never waits on it; stderr goes beside the report for debugging."""
    out = open(out_path, "w")
    err = open(str(out_path) + ".err", "w")
    proc = subprocess.Popen(argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                            cwd=cwd, start_new_session=True)
    return proc.pid


SPAWN = _spawn   # tests replace this


def launch(state, pr, rounds, cap, out_dir, now):
    """Start a drift review for `pr` unless one already ran (or is running) for this head."""
    runs = state.setdefault("drift_runs", {})
    head = (state["prs"].get(str(pr)) or {}).get("head")
    prior = runs.get(str(pr))
    if prior and prior.get("head") == head:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pr-{pr}-{now.replace(':', '')}.md"
    argv = ["claude", "--name", f"drift-pr-{pr}", "-p", prompt_for(pr, rounds, cap),
            "--output-format", "text",
            "--allowedTools", *ALLOWED_TOOLS]
    pid = SPAWN(argv, path, REPO_DIR)
    runs[str(pr)] = {"pid": pid, "path": str(path), "head": head, "started": now, "done": False}
    return runs[str(pr)]


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


ALIVE = _alive   # tests replace this


def verdict_of(path):
    try:
        first = Path(path).read_text().lstrip().splitlines()[0]
    except (OSError, IndexError):
        return None
    for v in VERDICTS:
        if first.strip() == f"VERDICT: {v}":
            return v
    return None


def collect(state):
    """Mark finished runs done; return [(pr, run)] that finished since the last call."""
    finished = []
    for pr, run in (state.get("drift_runs") or {}).items():
        if run.get("done") or ALIVE(run["pid"]):
            continue
        run["done"] = True
        run["verdict"] = verdict_of(run["path"])
        finished.append((int(pr), run))
    return finished
