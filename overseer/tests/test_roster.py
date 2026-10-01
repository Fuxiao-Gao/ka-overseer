# overseer/tests/test_roster.py
import json
import roster as R

RAW = [
    {"pid": 1, "cwd": "/x", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "a", "name": "kube-agents-vamp-d4", "status": "busy"},
    {"pid": 2, "cwd": "/x", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "b", "name": "home", "status": "idle"},
    {"pid": 3, "cwd": "/x", "kind": "bg", "startedAt": 1790000000000, "sessionId": "c", "name": "overseer-spike", "status": "waiting"},
    {"pid": 4, "cwd": "/x", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "d", "name": "kube-agents-vamp-1", "status": "waiting"},
]


def test_filter_keeps_scope_and_converts_time():
    out = R.filter_roster(RAW)
    assert [a["name"] for a in out] == ["kube-agents-vamp-1", "kube-agents-vamp-d4", "overseer-spike"]
    assert out[0] == {"name": "kube-agents-vamp-1", "status": "waiting", "kind": "interactive", "started_at": "2026-09-21T14:13:20Z"}


def test_newly_waiting_transitions():
    cur = R.filter_roster(RAW)
    assert R.newly_waiting(None, cur) == ["kube-agents-vamp-1", "overseer-spike"]   # first pass: notify once
    assert R.newly_waiting(cur, cur) == []                                         # steady: silent
    prev = [dict(a, status="busy") if a["name"] == "kube-agents-vamp-1" else a for a in cur]
    assert R.newly_waiting(prev, cur) == ["kube-agents-vamp-1"]                    # re-entered: notify again


def test_cli_writes_roster_and_prints_new_waiting(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "read_roster", lambda: R.filter_roster(RAW))
    fired = []
    monkeypatch.setattr(R, "notify", lambda title, text: fired.append(text))
    out = tmp_path / "roster.json"
    R.main(["--out", str(out), "--notify"])
    saved = json.loads(out.read_text())
    assert [a["name"] for a in saved["sessions"]] == ["kube-agents-vamp-1", "kube-agents-vamp-d4", "overseer-spike"]
    assert saved["ts"].endswith("Z")
    assert len(fired) == 2
    fired.clear()
    R.main(["--out", str(out), "--notify"])
    assert fired == []


def test_entry_without_status_is_kept_as_unknown_not_a_crash():
    raw = RAW + [{"pid": 9, "cwd": "/x", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "e", "name": "kube-agents-vamp-new"}]
    out = R.filter_roster(raw)
    row = next(a for a in out if a["name"] == "kube-agents-vamp-new")
    assert row["status"] == "unknown"
    assert "kube-agents-vamp-new" not in R.newly_waiting(None, out)


def test_duplicate_names_keep_the_oldest_and_suffix_the_rest():
    raw = RAW + [{"pid": 11, "cwd": "/x", "kind": "interactive", "startedAt": 1790000500000, "sessionId": "z", "name": "kube-agents-vamp-d4", "status": "waiting"}]
    out = R.filter_roster(raw)
    names = [a["name"] for a in out]
    assert names.count("kube-agents-vamp-d4") == 1
    assert "kube-agents-vamp-d4~2" in names
    assert next(a for a in out if a["name"] == "kube-agents-vamp-d4")["status"] == "busy"      # the older one keeps the name


def test_sessions_in_a_kube_agents_checkout_are_in_scope_whatever_their_name():
    raw = RAW + [{"pid": 12, "cwd": "/Users/bnaylor/src/kube-agents-fork/.worktrees/sessions-p1", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "w", "name": "sessions-p1-59", "status": "busy"},
                 {"pid": 13, "cwd": "/Users/bnaylor/src/iris", "kind": "interactive", "startedAt": 1790000000000, "sessionId": "i", "name": "iris-7e", "status": "idle"}]
    names = [a["name"] for a in R.filter_roster(raw)]
    assert "sessions-p1-59" in names and "iris-7e" not in names and "home" not in names
