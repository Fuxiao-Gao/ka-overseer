# overseer/tests/test_ovsr.py
import json
import io
from pathlib import Path

import ovsr
import state as S

REPORT = "OVERSEER REPORT kube-agents-vamp-54\nrole: pr-minder | theme: budget | driver: loop/30m | mode: auto\nprs: #2077 round 5\nstatus: waiting-human: which side moves\nrules: 9\n"


def setup(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "rules.md").write_text("# Overseer rules\n\n## Rules\n\n1. one\n2. two\n")
    tmp_path = tmp_path / "overseer"; tmp_path.mkdir(exist_ok=True)
    monkeypatch.setattr(ovsr, "notify", lambda title, text: ovsr.FIRED.append(text))
    ovsr.FIRED.clear()
    return str(tmp_path)


def test_report_appends_log_applies_and_renders(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(REPORT))
    assert ovsr.main(["--dir", d, "report"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["session"] == "kube-agents-vamp-54" and len(out["new_attention"]) == 1
    assert (Path(d) / "reports.log").read_text().count("\n") == 1
    assert (Path(d) / "dashboard.html").exists()
    assert S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-54"]["role"] == "pr-minder"
    assert ovsr.FIRED == ["kube-agents-vamp-54: which side moves"]


def test_unparseable_report_exits_2(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("hi"))
    assert ovsr.main(["--dir", d, "report", "--from", "kube-agents-vamp-9"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert (Path(d) / "reports.log").read_text().count("\n") == 1   # still logged


def test_tick_without_gh_applies_roster_and_computes_actions(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    (Path(d) / "roster.json").write_text(json.dumps({"ts": "2026-10-01T20:00:00Z", "sessions": [
        {"name": "kube-agents-vamp-7", "status": "idle", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}]}))
    assert ovsr.main(["--dir", d, "tick", "--no-gh", "--session", "kube-agents-vamp-65", "--next-wake", "2026-10-01T20:15:00Z"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [a["type"] for a in out["actions"]] == ["INTRO"]
    assert len(out["summary"]) <= 5
    st = S.load_state(Path(d) / "state.json")
    assert st["overseer"] == {"session": "kube-agents-vamp-65", "tick": 1, "next_wake": "2026-10-01T20:15:00Z"}
    assert st["sessions"]["kube-agents-vamp-7"]["roster_status"] == "idle"


def test_tick_notifies_new_attention_once(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    (Path(d) / "roster.json").write_text(json.dumps({"ts": "2026-10-01T20:00:00Z", "sessions": [
        {"name": "kube-agents-vamp-7", "status": "waiting", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}]}))
    ovsr.main(["--dir", d, "tick", "--no-gh"])
    ovsr.main(["--dir", d, "tick", "--no-gh"])
    # the watcher owns the `waiting` notification; the tick records the item but stays quiet
    assert ovsr.FIRED == []
    items = S.load_state(Path(d) / "state.json")["attention"]
    assert [i["kind"] for i in items] == ["waiting"] and items[0]["notified"] is True
    monkeypatch.setattr("sys.stdin", io.StringIO("OVERSEER REPORT kube-agents-vamp-7\nstatus: waiting-human: q\n"))
    ovsr.main(["--dir", d, "report"])
    ovsr.main(["--dir", d, "tick", "--no-gh"])
    assert ovsr.FIRED == ["kube-agents-vamp-7: q"]                                  # other kinds notify once


def test_rule_appends_and_bumps_version(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    assert ovsr.main(["--dir", d, "rule", "No pushes after 5pm Friday."]) == 0
    assert capsys.readouterr().out.strip() == "RULE 3: No pushes after 5pm Friday."
    assert (Path(d).parent / "docs" / "rules.md").read_text().rstrip().endswith("3. No pushes after 5pm Friday.")
    assert S.load_state(Path(d) / "state.json")["rules_version"] == 3


def test_assign_sets_owner_and_prints_message(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    assert ovsr.main(["--dir", d, "assign", "2077", "kube-agents-vamp-7", "--hazards", "edits manifests.go"]) == 0
    msg = capsys.readouterr().out
    assert msg.startswith("ASSIGN #2077") and "edits manifests.go" in msg
    st = S.load_state(Path(d) / "state.json")
    assert st["prs"]["2077"]["owner"] == "kube-agents-vamp-7" and st["prs"]["2077"]["hazards"] == "edits manifests.go"


def test_sent_retire_clear_intro(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(REPORT))
    ovsr.main(["--dir", d, "report"])
    capsys.readouterr()
    assert ovsr.main(["--dir", d, "sent", "PING", "kube-agents-vamp-54"]) == 0
    st = S.load_state(Path(d) / "state.json")
    assert st["sessions"]["kube-agents-vamp-54"]["ladder"] == 0 and st["sessions"]["kube-agents-vamp-54"]["last_poke"]
    assert ovsr.main(["--dir", d, "clear", "kube-agents-vamp-54:waiting-human:-"]) == 0
    assert S.load_state(Path(d) / "state.json")["attention"] == []
    assert ovsr.main(["--dir", d, "intro", "kube-agents-vamp-54"]) == 0
    intro = capsys.readouterr().out
    assert intro.startswith("INTRO") and "Skill tool" in intro and "working-with-the-overseer" in intro
    assert ovsr.main(["--dir", d, "retire", "kube-agents-vamp-54"]) == 0
    assert "kube-agents-vamp-54" not in S.load_state(Path(d) / "state.json")["sessions"]


def test_rebuild_from_log(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(REPORT))
    ovsr.main(["--dir", d, "report"])
    (Path(d) / "state.json").unlink()
    assert ovsr.main(["--dir", d, "rebuild"]) == 0
    assert S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-54"]["role"] == "pr-minder"


def test_tick_never_intros_the_overseer_itself(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    (Path(d) / "roster.json").write_text(json.dumps({"ts": "2026-10-01T20:00:00Z", "sessions": [
        {"name": "kube-agents-vamp-65", "status": "busy", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"},
        {"name": "kube-agents-vamp-7", "status": "idle", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}]}))
    ovsr.main(["--dir", d, "tick", "--no-gh", "--session", "kube-agents-vamp-65"])
    out = json.loads(capsys.readouterr().out)
    assert [a["session"] for a in out["actions"]] == ["kube-agents-vamp-7"]


def test_tick_fills_in_the_overseers_own_row(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    (Path(d) / "roster.json").write_text(json.dumps({"ts": "2026-10-01T20:00:00Z", "sessions": [
        {"name": "kube-agents-vamp-65", "status": "busy", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}]}))
    ovsr.main(["--dir", d, "tick", "--no-gh", "--session", "kube-agents-vamp-65"])
    me = S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-65"]
    assert me["role"] == "overseer" and me["status"] == "working" and me["last_report"] and me["rules_ack"] == 9


def test_report_refreshes_drift_without_a_github_pull(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    st = S.empty_state()
    S.pr(st, 2077).update(rounds=6, unresolved_threads=0, hold=False, owner="kube-agents-vamp-54",
                          owner_belief={"rounds": 5, "threads": 0, "hold": True}, drift="owner says rounds 5, GitHub 6; owner says hold, GitHub has no hold")
    S.save_state(st, Path(d) / "state.json")
    monkeypatch.setattr("sys.stdin", io.StringIO("OVERSEER REPORT kube-agents-vamp-54\nprs: #2077 round 6 0-threads no-hold\nstatus: working\n"))
    ovsr.main(["--dir", d, "report"])
    assert S.load_state(Path(d) / "state.json")["prs"]["2077"]["drift"] is None


def test_sent_ping_records_the_poke_without_a_second_ladder_bump(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    st = S.empty_state()
    S.session(st, "kube-agents-vamp-1").update(status="working", roster_status="idle", cadence_min=30, prs=[5],
                                              last_report="2026-01-01T00:00:00Z", last_activity="2026-01-01T00:00:00Z")
    S.pr(st, 5).update(owner="kube-agents-vamp-1", state="OPEN", checks="green", unresolved_threads=0, rounds=1,
                       last_activity="2026-01-02T00:00:00Z")
    S.save_state(st, Path(d) / "state.json")
    (Path(d) / "roster.json").write_text(json.dumps({"ts": S.now_iso(), "sessions": [
        {"name": "kube-agents-vamp-1", "status": "idle", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}]}))
    ovsr.main(["--dir", d, "tick", "--no-gh"])
    assert S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-1"]["ladder"] == 1
    ovsr.main(["--dir", d, "sent", "PING", "kube-agents-vamp-1"])
    assert S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-1"]["ladder"] == 1


def test_report_from_mismatch_is_rejected(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("OVERSEER REPORT kube-agents-vamp-54\nprs: #77 round 1\nstatus: working\n"))
    assert ovsr.main(["--dir", d, "report", "--from", "kube-agents-vamp-99"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "kube-agents-vamp-54" in out["error"] and "kube-agents-vamp-99" in out["error"]
    assert "kube-agents-vamp-54" not in S.load_state(Path(d) / "state.json")["sessions"]


def test_unknown_status_is_rejected_with_exit_2(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("OVERSEER REPORT kube-agents-vamp-9\nstatus: blocked: need a decision\n"))
    assert ovsr.main(["--dir", d, "report"]) == 2
    assert "status" in json.loads(capsys.readouterr().out)["error"]


def test_stale_or_corrupt_roster_file_falls_back_to_a_live_read(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(ovsr, "_live_roster", lambda: [{"name": "kube-agents-vamp-1", "status": "busy", "kind": "interactive", "started_at": "2026-01-01T00:00:00Z"}])
    (Path(d) / "roster.json").write_text(json.dumps({"ts": "2026-01-01T00:00:00Z", "sessions": []}))   # stale
    ovsr.main(["--dir", d, "tick", "--no-gh"])
    assert S.load_state(Path(d) / "state.json")["sessions"]["kube-agents-vamp-1"]["roster_status"] == "busy"
    (Path(d) / "roster.json").write_text("{not json")                                                  # torn write
    assert ovsr.main(["--dir", d, "tick", "--no-gh"]) == 0


def test_attention_command_opens_a_manual_item_once_and_notifies(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    assert ovsr.main(["--dir", d, "attention", "kube-agents-vamp-d4", "drift-check", "1884", "15 gating rounds; re-evaluate for drift"]) == 0
    assert ovsr.main(["--dir", d, "attention", "kube-agents-vamp-d4", "drift-check", "1884", "15 gating rounds; re-evaluate for drift"]) == 1
    items = S.load_state(Path(d) / "state.json")["attention"]
    assert [i["id"] for i in items] == ["kube-agents-vamp-d4:drift-check:1884"]
    assert ovsr.FIRED == ["kube-agents-vamp-d4: 15 gating rounds; re-evaluate for drift"]
    assert ovsr.main(["--dir", d, "attention", "-", "orphan", "1885", "no driver"]) == 0
    assert S.load_state(Path(d) / "state.json")["attention"][1]["session"] == "-"


def test_runtime_dir_is_created_on_first_use(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ovsr, "notify", lambda title, text: None)
    d = tmp_path / "fresh" / "overseer"
    assert ovsr.main(["--dir", str(d), "intro", "some-session"]) == 0
    assert (d / "state.json").exists()


def test_tick_writes_a_one_line_overseer_name_file(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    (Path(d) / "roster.json").write_text(json.dumps({"ts": S.now_iso(), "sessions": []}))
    ovsr.main(["--dir", d, "tick", "--no-gh", "--session", "kube-agents-vamp-65"])
    assert (Path(d) / "OVERSEER").read_text() == "kube-agents-vamp-65\n"


def test_decision_command_logs_and_prints_a_verbatim_decision(tmp_path, monkeypatch, capsys):
    d = setup(tmp_path, monkeypatch)
    assert ovsr.main(["--dir", d, "decision", "kube-agents-vamp-d4", "1884", "I agree with the push and the split."]) == 0
    out = capsys.readouterr().out
    assert out.startswith("DECISION from the human via the Overseer") and '"I agree with the push and the split."' in out and "#1884" in out
    log = (Path(d) / "decisions.log").read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])["to"] == "kube-agents-vamp-d4" and json.loads(log[0])["quote"] == "I agree with the push and the split."
