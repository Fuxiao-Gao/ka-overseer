"""Overseer state: the single source of truth in state.json. Only ovsr.py writes it."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from report import parse_report

SESSION_STATUSES = {"working", "waiting-human", "waiting-review", "idle"}
RECENT_REPORT_MIN = 2   # a report this fresh proves the session is alive even if the roster file lacks it
GONE_SWEEP_MIN = 10     # gone this long: a restart or rename, not a blip; its question and PR claims are moot
ROSTER_STATUSES = {"busy", "idle", "waiting", "shell", "gone"}
OPEN_PR_STATES = {None, "OPEN"}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def empty_state():
    return {"updated": None, "rules_version": 9,
            "overseer": {"session": None, "tick": 0, "next_wake": None},
            "sessions": {}, "prs": {}, "attention": [], "retired": []}


def load_state(path):
    path = Path(path)
    if not path.exists():
        return empty_state()
    s = empty_state()
    s.update(json.loads(path.read_text()))
    s["overseer"] = {**empty_state()["overseer"], **(s.get("overseer") or {})}
    s["sessions"] = {k: {**_session_row(), **v} for k, v in s["sessions"].items()}
    s["prs"] = {k: {**_pr_row(), **v} for k, v in s["prs"].items()}
    return s


def save_state(state, path):
    state["updated"] = state.get("updated") or now_iso()
    write_atomic(path, json.dumps(state, indent=1, sort_keys=True) + "\n")


def write_atomic(path, text):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _session_row():
    return {"role": None, "theme": None, "driver": None, "cadence_min": None, "mode": None,
            "rules_ack": None, "prs": [], "status": None, "roster_status": None, "kind": None,
            "needs": None, "status_detail": None, "last_report": None, "last_activity": None, "last_poke": None,
            "started_at": None, "gone_since": None, "ladder": 0, "note": None}


def _pr_row():
    return {"owner": None, "title": None, "head": None, "branch": None, "url": None,
            "state": None, "mergeable": None, "checks": None, "unresolved_threads": None,
            "rounds": None, "rounds_prev": None, "advisory_rounds": None, "hold": None, "lgtm": None,
            "approved": None, "reviewers": [], "last_activity": None, "updated_at": None,
            "last_owner_report": None, "owner_belief": None, "drift": None,
            "snapshot_error": None, "hazards": None}


def session(state, name):
    return state["sessions"].setdefault(name, _session_row())


def pr(state, number):
    return state["prs"].setdefault(str(number), _pr_row())


def attention_id(session_name, kind, pr_number):
    return f"{session_name}:{kind}:{pr_number if pr_number is not None else '-'}"


def add_attention(state, session_name, kind, pr_number, what, now):
    item_id = attention_id(session_name, kind, pr_number)
    if any(i["id"] == item_id for i in state["attention"]):
        return None
    item = {"id": item_id, "session": session_name, "kind": kind, "pr": pr_number,
            "since": now, "what": what, "notified": False}
    state["attention"].append(item)
    return item


def clear_attention(state, item_id):
    before = len(state["attention"])
    state["attention"] = [i for i in state["attention"] if i["id"] != item_id]
    return len(state["attention"]) != before


def _clear_kind(state, session_name, kind):
    state["attention"] = [i for i in state["attention"]
                          if not (i["session"] == session_name and i["kind"] == kind)]


def apply_report(state, report, now):
    new = []
    name = report["session"]
    row = session(state, name)
    for k in ("role", "theme", "driver", "cadence_min", "mode", "note"):
        if report.get(k) is not None:
            row[k] = report[k]
    if report.get("rules") is not None:
        row["rules_ack"] = report["rules"]
    row["last_report"] = now
    row["last_activity"] = now
    row["ladder"] = 0
    for kind in ("stalled", "red", "threads"):      # the session spoke: silence-driven items are moot
        _clear_kind(state, name, kind)
    if report.get("status"):
        row["status"] = report["status"]
        row["needs"] = report.get("needs")
        row["status_detail"] = report.get("status_detail")
    # PR ownership
    reported = sorted(report["prs"])
    for old in row["prs"]:
        if old not in reported and state["prs"].get(str(old), {}).get("owner") == name:
            claimants = [n for n, r in state["sessions"].items() if n != name and old in r["prs"]]
            state["prs"][str(old)]["owner"] = claimants[0] if claimants else None
    row["prs"] = reported
    for number, belief in report["prs"].items():
        p = pr(state, number)
        if p["owner"] not in (None, name):
            other = p["owner"]
            if _is_live(state, other) and number in state["sessions"][other]["prs"]:   # a gone owner cannot drive it
                item = add_attention(state, name, "ownership-conflict", number,
                                     f"#{number} reported by both {other} and {name}; {name} now owner", now)
                if item:
                    new.append(item)
        p["owner"] = name
        p["last_owner_report"] = now
        p["owner_belief"] = {"rounds": belief["rounds"], "threads": belief["threads"], "hold": belief["hold"]}
    # attention for waiting-human
    if row["status"] == "waiting-human":
        what = row["needs"] or "waiting on the human"
        named = re.search(r"#(\d+)", what)
        pr_number = int(named.group(1)) if named else (reported[0] if reported else None)
        item = add_attention(state, name, "waiting-human", None, what, now)   # one item per session
        if item is None:
            existing = next(i for i in state["attention"] if i["id"] == attention_id(name, "waiting-human", None))
            if existing["what"] != what:          # a new question: refresh and notify again
                existing.update(what=what, since=now, notified=False)
                item = existing
            existing["pr"] = pr_number
        else:
            item["pr"] = pr_number
        if item:
            new.append(item)
    else:
        _clear_kind(state, name, "waiting-human")
    sweep(state, now)
    state["updated"] = now
    return new


def _owned_open_prs(state, name):
    return [int(n) for n, p in state["prs"].items()
            if p["owner"] == name and p.get("state") in OPEN_PR_STATES]


def _gone(row):
    """Gone from the roster and silent since; a report after leaving proves it is back before the watcher sees it."""
    return row["roster_status"] == "gone" and not (
        row["last_report"] and row["gone_since"] and parse_iso(row["last_report"]) > parse_iso(row["gone_since"]))


def _is_live(state, name):
    return name in state["sessions"] and not _gone(state["sessions"][name])


def _settled(state, now):
    return {n for n, r in state["sessions"].items()
            if _gone(r) and r["gone_since"]
            and parse_iso(now) - parse_iso(r["gone_since"]) >= timedelta(minutes=GONE_SWEEP_MIN)}


def sweep(state, now):
    """Drop attention items the facts have overtaken; runs after every report and roster pass.

    Hand-raised items (`ovsr.py attention`, marked `manual`) are never touched here. A session gone
    GONE_SWEEP_MIN loses its waiting-human item and its PR claims; an orphan item stays
    while its PRs have no live claimant, so a PR that really lost its owner still surfaces.
    """
    settled = _settled(state, now)

    def claimants(number):
        return [n for n, r in state["sessions"].items() if number in r["prs"] and n not in settled]

    for name in settled:
        state["attention"] = [i for i in state["attention"]
                              if i.get("manual") or not (i["session"] == name and i["kind"] == "waiting-human")]
        for number in _owned_open_prs(state, name):
            heirs = [n for n in claimants(number) if _is_live(state, n)]   # never to another absent session
            if heirs:
                state["prs"][str(number)]["owner"] = heirs[0]
    for item in list(state["attention"]):
        if item.get("manual"):
            continue
        if item["kind"] == "ownership-conflict" and item["pr"] is not None and len(claimants(item["pr"])) <= 1:
            state["attention"].remove(item)
        elif item["kind"] == "orphan" and not _owned_open_prs(state, item["session"]):
            state["attention"].remove(item)


def apply_roster(state, roster, now):
    new = []
    seen = set()
    returned = []
    for a in roster:
        name = a["name"]
        seen.add(name)
        row = session(state, name)
        if row["roster_status"] == "gone":
            returned.append(name)
        row["kind"] = a.get("kind")
        row["started_at"] = a.get("started_at") or row["started_at"]
        if row["roster_status"] != a["status"]:
            row["last_activity"] = now
        row["roster_status"] = a["status"]
        row["gone_since"] = None
        _clear_kind(state, name, "orphan")
        if a["status"] == "waiting":
            already = any(i["session"] == name and i["kind"] in ("waiting-bnaylor", "waiting-human") for i in state["attention"])
            if not already:                          # the session announced this stall itself; one item is enough
                owned = _owned_open_prs(state, name)
                item = add_attention(state, name, "waiting", owned[0] if owned else None,
                                     "parked on a question or prompt", now)
                if item:
                    new.append(item)
        else:
            _clear_kind(state, name, "waiting")
    for name in returned:          # a claim made while it was away raised no conflict against it; check now
        for number in state["sessions"][name]["prs"]:
            owner = state["prs"].get(str(number), {}).get("owner")
            if owner not in (None, name) and _is_live(state, owner) and number in state["sessions"][owner]["prs"]:
                item = add_attention(state, owner, "ownership-conflict", number,
                                     f"#{number} reported by both {name} and {owner}; {owner} now owner", now)
                if item:
                    new.append(item)
    for name, row in state["sessions"].items():
        if name in seen or _gone(row):     # a gone row that reported since is marked afresh once the report ages
            continue
        recent = row["last_report"] and parse_iso(now) - parse_iso(row["last_report"]) < timedelta(minutes=RECENT_REPORT_MIN)
        if recent:                                   # it just spoke; the watcher has not caught up yet
            continue
        row["roster_status"] = "gone"
        row["gone_since"] = now
        _clear_kind(state, name, "waiting")
        owned = _owned_open_prs(state, name)
        if owned:
            item = add_attention(state, name, "orphan", owned[0],
                                 f"session gone, owns {', '.join('#%d' % n for n in owned)}; reassign?", now)
            if item:
                new.append(item)
    sweep(state, now)
    state["updated"] = now
    return new


def retire(state, name, now):
    row = state["sessions"].pop(name, None)
    if row is None:
        return False
    state["attention"] = [i for i in state["attention"] if i["session"] != name]
    state["retired"].append({"session": name, "role": row["role"], "theme": row["theme"],
                             "retired_at": now, "prs_at_exit": row["prs"]})
    for p in state["prs"].values():
        if p["owner"] == name:
            p["owner"] = None
    return True


def retire_due(state, now, hours=24, ephemeral_hours=1):
    """Gone sessions retire after `hours`; ones that never reported and own nothing after `ephemeral_hours`."""
    due = []
    for name, row in state["sessions"].items():
        if not _gone(row) or not row["gone_since"] or _owned_open_prs(state, name):
            continue
        grace = ephemeral_hours if row["last_report"] is None else hours
        if parse_iso(row["gone_since"]) <= parse_iso(now) - timedelta(hours=grace):
            due.append(name)
    for name in due:
        retire(state, name, now)
    return due


def append_log(log_path, sender, raw, now):
    with Path(log_path).open("a") as f:
        f.write(json.dumps({"ts": now, "from": sender, "raw": raw}) + "\n")


def rebuild_from_log(log_path):
    state = empty_state()
    path = Path(log_path)
    if not path.exists():
        return state
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        report = parse_report(entry["raw"])
        if report:
            apply_report(state, report, entry["ts"])
    return state
