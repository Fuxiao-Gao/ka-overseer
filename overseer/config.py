"""Deployment settings. Edit overseer/config.json; nothing else needs to change for a new team."""
import json
from pathlib import Path

DEFAULTS = {
    "repo": "owner/repo",
    "human": "the human",
    "human_short": "human",
    "session_pattern": "^(kube-agents-|overseer)",
    "cwd_prefixes": [],
    "gating_bot": "kube-agents-bot",
    "advisory_bot": "kyber775",
    "round_cap": 6,
    "ignored_check_contexts": ["tide", "pull-kube-agents-smoke-test-next"],
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
