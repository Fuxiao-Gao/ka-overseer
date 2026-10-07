"""Drift review: when a PR crosses the round cap, a headless `claude -p` reads its review history
and writes a verdict for the human. One run per PR head.

The PR text is written by anyone who can comment, so the agent gets no network or write path at
all. A detached wrapper (`python3 drift.py run ...`) first fetches the history with fixed read-only
gh calls into a bundle directory, then execs claude in that directory with Read/Grep/Glob only.
The report goes to stdout, which the spawn redirects to a file.

State lives in state["drift_runs"][pr] = {pid, path, head, started, done}.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from config import CFG

PROMPT = Path(__file__).with_name("drift-prompt.md")
ALLOWED_TOOLS = ["Read", "Grep", "Glob"]   # nothing that writes, runs commands, or reaches the network
VERDICTS = ("CONVERGED", "CONVERGING", "SPIRALLING", "STALLED-ON-HUMAN")
MAX_COMMITS = 80
MAX_PATCH = 6000   # chars per file patch; the agent classifies findings, it doesn't re-review

THREADS_QUERY = """query($owner:String!,$name:String!,$pr:Int!){repository(owner:$owner,name:$name){
pullRequest(number:$pr){userContentEdits(first:100){nodes{createdAt diff}}
reviewThreads(first:100){nodes{isResolved isOutdated path line
comments(first:50){nodes{author{login} body createdAt url}}}}}}}"""


def prompt_for(pr, rounds, cap):
    return PROMPT.read_text().format(pr=pr, rounds=rounds, cap=cap, repo=CFG["repo"],
                                     gating_bot=CFG["gating_bot"], human=CFG["human"])


def claude_argv(pr, rounds, cap):
    return ["claude", "--name", f"drift-pr-{pr}", "-p", prompt_for(pr, rounds, cap),
            "--output-format", "text",
            # --restricted ignores user/project/local settings (so no inherited allow rules) and
            # confines the file tools to the cwd, which is the bundle; --tools is the whole tool set
            "--restricted", "--strict-mcp-config", "--tools", ",".join(ALLOWED_TOOLS),
            "--allowedTools", *ALLOWED_TOOLS]


def _gh(args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


GH = _gh   # tests replace this


def gather(pr, repo, bundle):
    """Fetch the PR's review history into `bundle`. Every call is a fixed read-only argv."""
    bundle = Path(bundle)
    (bundle / "commits").mkdir(parents=True, exist_ok=True)
    owner, name = repo.split("/", 1)
    view = GH(["pr", "view", str(pr), "-R", repo, "--json",
               "title,body,closingIssuesReferences,commits,reviews,comments,createdAt,additions,deletions,headRefOid"])
    (bundle / "pr.json").write_text(view)
    meta = json.loads(view)
    g = json.loads(GH(["api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"owner={owner}",
                       "-F", f"name={name}", "-F", f"pr={int(pr)}"]))
    p = g["data"]["repository"]["pullRequest"]
    (bundle / "threads.json").write_text(json.dumps(p["reviewThreads"]["nodes"], indent=1))
    (bundle / "body_edits.json").write_text(json.dumps(p["userContentEdits"]["nodes"], indent=1))
    for issue in meta.get("closingIssuesReferences") or []:
        n = int(issue["number"])
        (bundle / f"issue-{n}.json").write_text(GH(["issue", "view", str(n), "-R", repo, "--json", "title,body"]))
    for c in (meta.get("commits") or [])[-MAX_COMMITS:]:
        sha = c["oid"]
        if not all(ch in "0123456789abcdef" for ch in sha):
            continue
        full = json.loads(GH(["api", f"repos/{owner}/{name}/commits/{sha}"]))
        files = [{"filename": f.get("filename"), "status": f.get("status"),
                  "additions": f.get("additions"), "deletions": f.get("deletions"),
                  "patch": _cut(f.get("patch") or "")} for f in full.get("files") or []]
        (bundle / "commits" / f"{sha}.json").write_text(json.dumps(
            {"sha": sha, "message": full.get("commit", {}).get("message"),
             "date": full.get("commit", {}).get("committer", {}).get("date"), "files": files}, indent=1))
    try:
        checks = GH(["pr", "checks", str(pr), "-R", repo, "--json", "name,state,link"])
    except subprocess.CalledProcessError as e:   # gh exits non-zero while checks are pending or red
        checks = e.stdout or "[]"
    (bundle / "checks.json").write_text(checks)


def _cut(patch):
    return patch if len(patch) <= MAX_PATCH else patch[:MAX_PATCH] + f"\n[... cut, {len(patch) - MAX_PATCH} more chars]"


def run(pr, rounds, cap, bundle):
    """The detached wrapper: gather, then become claude inside the bundle."""
    gather(pr, CFG["repo"], bundle)
    os.chdir(bundle)
    argv = claude_argv(pr, rounds, cap)
    os.execvp(argv[0], argv)


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
    bundle = Path(str(path)[:-3] + ".bundle")
    argv = [sys.executable, str(Path(__file__).resolve()), "run", "--pr", str(int(pr)),
            "--rounds", str(rounds), "--cap", str(cap), "--bundle", str(bundle)]
    pid = SPAWN(argv, path, str(Path(__file__).resolve().parent))
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
    for pr, run_ in (state.get("drift_runs") or {}).items():
        if run_.get("done") or ALIVE(run_["pid"]):
            continue
        run_["done"] = True
        run_["verdict"] = verdict_of(run_["path"])
        finished.append((int(pr), run_))
    return finished


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--pr", type=int, required=True)
    r.add_argument("--rounds", required=True)
    r.add_argument("--cap", required=True)
    r.add_argument("--bundle", required=True)
    a = ap.parse_args()
    run(a.pr, a.rounds, a.cap, a.bundle)
