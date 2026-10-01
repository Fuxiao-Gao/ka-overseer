"""One-shot transform applied when this package was extracted from the kube-agents-vamp repo. Kept for the record."""
import re, pathlib, json
root = pathlib.Path(__file__).resolve().parents[1]

config = {
  "repo": "gke-labs/kube-agents", "human": "the human", "human_short": "human",
  "session_pattern": "^(kube-agents-|overseer)", "gating_bot": "kube-agents-bot", "advisory_bot": "kyber775",
  "round_cap": 6, "ignored_check_contexts": ["tide"],
  "scope_queries": {"mine": ["--author", "@me"], "review_requested": ["--search", "review-requested:@me"],
                    "reviewed": ["--search", "reviewed-by:@me -author:@me"]},
  "notify": "osascript"}
(root/"overseer/config.json").write_text(json.dumps(config, indent=2) + "\n")
(root/"overseer/config.py").write_text('''"""Deployment settings. Edit overseer/config.json; nothing else needs to change for a new team."""
import json
from pathlib import Path

DEFAULTS = {
    "repo": "owner/repo",
    "human": "the human",
    "human_short": "human",
    "session_pattern": "^(kube-agents-|overseer)",
    "gating_bot": "kube-agents-bot",
    "advisory_bot": "kyber775",
    "round_cap": 6,
    "ignored_check_contexts": ["tide"],
    "scope_queries": {
        "mine": ["--author", "@me"],
        "review_requested": ["--search", "review-requested:@me"],
        "reviewed": ["--search", "reviewed-by:@me -author:@me"],
    },
    "notify": "osascript",
}


def load(path=None):
    cfg = dict(DEFAULTS)
    p = Path(path) if path else Path(__file__).with_name("config.json")
    if p.exists():
        cfg.update(json.loads(p.read_text()))
    return cfg


CFG = load()
''')

def sub(path, pairs, must=True):
    p = root/path; s = p.read_text()
    for old, new in pairs:
        if must: assert old in s, (path, old[:60])
        s = s.replace(old, new)
    p.write_text(s)

WB, WH = "waiting-bnaylor", "waiting-human"
for f in ["overseer/state.py", "overseer/render.py", "overseer/ovsr.py", "overseer/report.py", "overseer/signals.py",
          "overseer/tests/test_state.py", "overseer/tests/test_ovsr.py", "overseer/tests/test_report.py", "overseer/tests/test_render.py"]:
    sub(f, [(WB, WH)], must=False)

sub("overseer/report.py", [
('''            r["status"] = token.lower().replace("_", "-")''',
'''            r["status"] = token.lower().replace("_", "-")
            if r["status"].startswith("waiting-") and r["status"] != "waiting-review":
                r["status"] = "waiting-human"          # waiting-brian, waiting-user, ... all mean the same stall'''),
])
sub("overseer/state.py", [('row["needs"] or "waiting on Brian"', 'row["needs"] or "waiting on the human"')])
sub("overseer/signals.py", [("/request-review or ask Brian", "/request-review or ask the human")])
sub("overseer/gh_snapshot.py", [
('''REPO = "gke-labs/kube-agents"
GATING_BOT = "kube-agents-bot"
ADVISORY_BOT = "kyber775"
ROUND_CAP = 6''',
'''from config import CFG

REPO = CFG["repo"]
GATING_BOT = CFG["gating_bot"]
ADVISORY_BOT = CFG["advisory_bot"]
ROUND_CAP = int(CFG["round_cap"])'''),
('''IGNORED_CONTEXTS = {"tide"}  # merge-pool state, always PENDING until merge; not a CI check''',
'''IGNORED_CONTEXTS = set(CFG["ignored_check_contexts"])  # e.g. tide: merge-pool state, PENDING until merge, not a CI check'''),
('''def _numbers(cmd):
    out = _run(cmd + ["--json", "number", "--jq", ".[].number"])
    return [int(x) for x in out.split()]


MY_OPEN = str(Path.home() / "bin" / "my_open")
LIST_CMDS = {
    "prs": lambda: _numbers([MY_OPEN, "prs"]),
    "reviews": lambda: _numbers([MY_OPEN, "reviews"]),
    "reviewed": lambda: _numbers([MY_OPEN, "reviewed"]),
}''',
'''def _numbers(extra):
    out = _run(["gh", "pr", "list", "-R", REPO, "--state", "open", *extra, "--json", "number", "--jq", ".[].number"])
    return [int(x) for x in out.split()]


LIST_CMDS = {name: (lambda extra=extra: _numbers(extra)) for name, extra in CFG["scope_queries"].items()}'''),
])
sub("overseer/roster.py", [
('''SCOPE = re.compile(r"^(kube-agents-vamp-|overseer)")''', '''from config import CFG

SCOPE = re.compile(CFG["session_pattern"])'''),
])
sub("overseer/ovsr.py", [
('''from roster import notify as _osascript_notify''', '''from config import CFG
from roster import notify as _osascript_notify'''),
('''INTRO_TEXT = """INTRO from the Overseer ({me}). I track every kube-agents session, keep the dashboard, relay numbered rules, and poke stalled sessions. I may tell you to STOP only for a written rule; everything else is advice.
FIRST: invoke the skill `working-with-the-overseer` with the Skill tool — it is in your skill listing now — and follow it. If the listing does not show it yet, read ~/src/skills/working-with-the-overseer/SKILL.md. Rules: {dir}/rules.md. Dashboard: {dir}/dashboard.html.''',
'''INTRO_TEXT = """INTRO from the Overseer ({me}). I track every session working on {repo}, keep the dashboard, relay numbered rules, and poke stalled sessions. I may tell you to STOP only for a written rule; everything else is advice.
FIRST: invoke the skill `working-with-the-overseer` with the Skill tool — it is in your skill listing now — and follow it. If the listing does not show it yet, read {skill}. Rules: {rules}. Dashboard: {dir}/dashboard.html.'''),
('''From now on send me that report whenever your status or PR list changes, BEFORE you ask Brian anything (status waiting-human), before you stop a loop, and when I PING you."""''',
'''From now on send me that report whenever your status or PR list changes, BEFORE you ask {human} anything (status waiting-human), before you stop a loop, and when I PING you."""'''),
('''        self.rules = self.dir / "rules.md"''', '''        self.rules = self.dir.parent / "docs" / "rules.md"
        self.skill = self.dir.parent / "skills" / "working-with-the-overseer" / "SKILL.md"'''),
('''    print(INTRO_TEXT.format(me=state["overseer"].get("session") or "this session", dir=p.dir))''',
'''    print(INTRO_TEXT.format(me=state["overseer"].get("session") or "this session", dir=p.dir, repo=CFG["repo"],
                            human=CFG["human"], skill=p.skill, rules=p.rules))'''),
])
# tests: rules.md lives in <pkg>/docs; the CLI runtime dir is <pkg>/overseer
sub("overseer/tests/test_ovsr.py", [
('''    (tmp_path / "rules.md").write_text("# Overseer rules\\n\\n## Rules\\n\\n1. one\\n2. two\\n")''',
'''    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "rules.md").write_text("# Overseer rules\\n\\n## Rules\\n\\n1. one\\n2. two\\n")
    tmp_path = tmp_path / "overseer"; tmp_path.mkdir(exist_ok=True)'''),
])
s = (root/"overseer/tests/test_ovsr.py").read_text()
s = re.sub(r'tmp_path / "(state\.json|reports\.log|dashboard\.html|roster\.json)"', r'Path(d) / "\1"', s)
s = s.replace('(tmp_path / "rules.md").read_text().rstrip().endswith("3. No pushes after 5pm Friday.")',
              '(Path(d).parent / "docs" / "rules.md").read_text().rstrip().endswith("3. No pushes after 5pm Friday.")')
(root/"overseer/tests/test_ovsr.py").write_text(s)

for f in ["docs/protocol.md", "docs/escalation.md", "docs/rules.md", "skills/working-with-the-overseer/SKILL.md", "briefs/overseer-loop.txt", "docs/design.md"]:
    p = root/f; s = p.read_text()
    s = s.replace(WB, WH).replace("Brian's", "the human's").replace("Brian", "the human")
    s = s.replace("/Users/bnaylor/src/kube-agents-vamp/overseer/state.json", "<ka-overseer>/overseer/state.json")
    s = s.replace("/Users/bnaylor/src/kube-agents-vamp", "<ka-overseer>")
    s = s.replace("~/src/skills/working-with-the-overseer/SKILL.md", "<ka-overseer>/skills/working-with-the-overseer/SKILL.md")
    s = s.replace("`kube-agents-vamp-*`", "sessions matching `session_pattern` in `overseer/config.json`")
    s = s.replace("kube-agents-vamp-65", "<overseer-session>").replace("kube-agents-vamp-54", "<session-name>")
    s = s.replace("overseer/rules.md", "docs/rules.md").replace("overseer/protocol.md", "docs/protocol.md").replace("overseer/escalation.md", "docs/escalation.md")
    p.write_text(s)
sub("briefs/overseer-loop.txt", [
("be the Overseer for my kube-agents sessions.  Brief: overseer/overseer.md; design: overseer/design.md;\nwire format: docs/protocol.md; what to watch: docs/escalation.md.  Everything runs through\n`python3 overseer/ovsr.py`.",
 "be the Overseer for my coding-agent sessions.  Package: <ka-overseer> (cd there first).  Design:\ndocs/design.md; wire format: docs/protocol.md; what to watch: docs/escalation.md.  Everything runs\nthrough `python3 overseer/ovsr.py`."),
], must=False)
print("portify done")
