# overseer/tests/test_state.py
import json
from pathlib import Path

import state as S
from report import parse_report

T0 = "2026-10-01T20:00:00Z"
T1 = "2026-10-01T20:30:00Z"
T2 = "2026-10-03T00:00:00Z"


def report(text):
    return parse_report(text)


def test_empty_state_shape():
    s = S.empty_state()
    assert set(s) >= {"updated", "rules_version", "overseer", "sessions", "prs", "attention", "retired"}
    assert s["sessions"] == {} and s["attention"] == []


def test_apply_report_creates_session_and_pr_rows():
    s = S.empty_state()
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-54\nrole: pr-minder | theme: budget | driver: loop/30m | mode: auto\nprs: #2077 round 5 hold\nstatus: working\nrules: 7\n"), T0)
    row = s["sessions"]["kube-agents-vamp-54"]
    assert row["role"] == "pr-minder" and row["cadence_min"] == 30 and row["rules_ack"] == 7
    assert row["prs"] == [2077] and row["status"] == "working" and row["last_report"] == T0
    assert s["prs"]["2077"]["owner"] == "kube-agents-vamp-54"
    assert s["prs"]["2077"]["last_owner_report"] == T0
    assert s["prs"]["2077"]["owner_belief"] == {"rounds": 5, "threads": None, "hold": True}
    assert new == []


def test_waiting_bnaylor_opens_one_attention_item_and_working_clears_it():
    s = S.empty_state()
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-54\nprs: #2077 round 5\nstatus: waiting-human: which side moves\n"), T0)
    assert len(new) == 1
    item = new[0]
    assert item["id"] == "kube-agents-vamp-54:waiting-human:-" and item["pr"] == 2077
    assert item["what"] == "which side moves" and item["since"] == T0 and item["notified"] is False
    # same report again: no duplicate
    assert S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-54\nprs: #2077 round 5\nstatus: waiting-human: which side moves\n"), T1) == []
    assert len(s["attention"]) == 1
    # back to working clears it
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-54\nprs: #2077 round 5\nstatus: working\n"), T1)
    assert s["attention"] == []


def test_waiting_bnaylor_without_pr_uses_dash():
    s = S.empty_state()
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-7\nstatus: waiting-human: design call\n"), T0)
    assert new[0]["id"] == "kube-agents-vamp-7:waiting-human:-"


def test_report_from_unknown_session_before_roster_is_fine():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-99\nstatus: idle\n"), T0)
    assert s["sessions"]["kube-agents-vamp-99"]["roster_status"] is None


def test_ownership_conflict_last_reporter_wins_and_flags_once():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T0)
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-2\nprs: #5 round 1\nstatus: working\n"), T1)
    assert s["prs"]["5"]["owner"] == "kube-agents-vamp-2"
    assert [i["kind"] for i in new] == ["ownership-conflict"]
    assert S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-2\nprs: #5 round 1\nstatus: working\n"), T1) == []


def test_dropping_a_pr_from_the_list_releases_ownership():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1; #6 round 1\nstatus: working\n"), T0)
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #6 round 1\nstatus: working\n"), T1)
    assert s["prs"]["5"]["owner"] is None and s["prs"]["6"]["owner"] == "kube-agents-vamp-1"


def test_apply_roster_sets_status_marks_gone_and_opens_waiting_item():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T0)
    roster = [{"name": "kube-agents-vamp-1", "status": "waiting", "kind": "interactive", "started_at": T0},
              {"name": "kube-agents-vamp-3", "status": "idle", "kind": "interactive", "started_at": T0}]
    new = S.apply_roster(s, roster, T1)
    assert s["sessions"]["kube-agents-vamp-1"]["roster_status"] == "waiting"
    assert s["sessions"]["kube-agents-vamp-3"]["roster_status"] == "idle"
    assert s["sessions"]["kube-agents-vamp-3"]["status"] is None
    assert [i["id"] for i in new] == ["kube-agents-vamp-1:waiting:5"]
    # leaves the roster while owning #5 -> gone + orphan
    new = S.apply_roster(s, [roster[1]], T2)
    assert s["sessions"]["kube-agents-vamp-1"]["roster_status"] == "gone"
    assert s["sessions"]["kube-agents-vamp-1"]["status"] == "working"      # the self-report is kept for the record
    assert s["sessions"]["kube-agents-vamp-1"]["gone_since"] == T2
    assert [i["kind"] for i in new] == ["orphan"]
    # waiting item is cleared when the session is no longer waiting
    assert not any(i["kind"] == "waiting" for i in s["attention"])


def test_roster_status_change_bumps_last_activity():
    s = S.empty_state()
    S.apply_roster(s, [{"name": "kube-agents-vamp-1", "status": "busy", "kind": "interactive", "started_at": T0}], T0)
    S.apply_roster(s, [{"name": "kube-agents-vamp-1", "status": "busy", "kind": "interactive", "started_at": T0}], T1)
    assert s["sessions"]["kube-agents-vamp-1"]["last_activity"] == T0
    S.apply_roster(s, [{"name": "kube-agents-vamp-1", "status": "idle", "kind": "interactive", "started_at": T0}], T2)
    assert s["sessions"]["kube-agents-vamp-1"]["last_activity"] == T2


def test_retire_due_only_when_gone_long_enough_and_owning_nothing():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T0)
    S.apply_roster(s, [], T1)
    assert S.retire_due(s, T2) == []            # still owns #5
    s["prs"]["5"]["state"] = "MERGED"
    assert S.retire_due(s, T2) == ["kube-agents-vamp-1"]
    assert "kube-agents-vamp-1" not in s["sessions"]
    assert s["retired"][0]["session"] == "kube-agents-vamp-1" and s["retired"][0]["prs_at_exit"] == [5]


def test_explicit_retire_removes_its_attention_items():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nstatus: waiting-human: q\n"), T0)
    assert S.retire(s, "kube-agents-vamp-1", T1) is True
    assert s["attention"] == [] and S.retire(s, "nope", T1) is False


def test_save_load_roundtrip_and_rebuild_from_log(tmp_path: Path):
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T0)
    S.save_state(s, tmp_path / "state.json")
    assert S.load_state(tmp_path / "state.json")["prs"]["5"]["owner"] == "kube-agents-vamp-1"
    assert S.load_state(tmp_path / "missing.json")["sessions"] == {}
    log = tmp_path / "reports.log"
    log.write_text(json.dumps({"ts": T0, "from": "kube-agents-vamp-1", "raw": "OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"}) + "\n"
                   + json.dumps({"ts": T1, "from": "kube-agents-vamp-1", "raw": "OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 2\nstatus: idle\n"}) + "\n")
    r = S.rebuild_from_log(log)
    assert r["sessions"]["kube-agents-vamp-1"]["status"] == "idle"
    assert r["prs"]["5"]["owner_belief"]["rounds"] == 2


def test_parse_iso_accepts_z_and_offset():
    assert S.parse_iso("2026-10-01T20:00:00Z") == S.parse_iso("2026-10-01T20:00:00+00:00")


def test_load_state_backfills_new_row_fields(tmp_path: Path):
    (tmp_path / "state.json").write_text(json.dumps({"sessions": {"kube-agents-vamp-1": {"role": "task"}},
                                                     "prs": {"5": {"owner": "kube-agents-vamp-1", "rounds": 3}}}))
    s = S.load_state(tmp_path / "state.json")
    assert s["prs"]["5"]["rounds_prev"] is None and s["prs"]["5"]["rounds"] == 3
    assert s["sessions"]["kube-agents-vamp-1"]["ladder"] == 0 and s["sessions"]["kube-agents-vamp-1"]["role"] == "task"
    assert s["attention"] == [] and s["overseer"]["tick"] == 0


def test_ephemeral_gone_session_retires_after_an_hour():
    s = S.empty_state()
    S.apply_roster(s, [{"name": "kube-agents-vamp-69", "status": "busy", "kind": "interactive", "started_at": T0}], T0)
    S.apply_roster(s, [], "2026-10-01T20:10:00Z")
    assert S.retire_due(s, "2026-10-01T20:50:00Z") == []                 # 40 min gone: keep
    assert S.retire_due(s, "2026-10-01T21:20:00Z") == ["kube-agents-vamp-69"]   # never reported, owns nothing: 1 h
    # a session that did report keeps the 24 h grace
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nstatus: working\n"), T0)
    S.apply_roster(s, [], T1)
    assert S.retire_due(s, "2026-10-01T23:00:00Z") == []
    assert S.retire_due(s, T2) == ["kube-agents-vamp-1"]


def test_changed_waiting_bnaylor_question_updates_item_and_renotifies():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1935 round 6\nstatus: waiting-human: file an issue?\n"), T0)
    s["attention"][0]["notified"] = True
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1935 round 8\nstatus: waiting-human: add a pending cap or defer?\n"), T1)
    assert len(s["attention"]) == 1
    item = s["attention"][0]
    assert item["what"] == "add a pending cap or defer?" and item["notified"] is False and item["since"] == T1
    assert new == [item]


def test_dropping_a_pr_hands_it_back_to_a_session_that_still_lists_it():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-da\nprs: #1979 round 0\nstatus: working\n"), T0)
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1935 round 6; #1979 round 0\nstatus: working\n"), T0)
    assert s["prs"]["1979"]["owner"] == "kube-agents-vamp-20"
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1935 round 6\nstatus: working\n"), T1)
    assert s["prs"]["1979"]["owner"] == "kube-agents-vamp-da"


def test_absent_from_roster_keeps_self_reported_status_and_recent_reporters_are_not_gone():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: waiting-human: q\n"), T0)
    # reported 30 s ago, not yet in the watcher's roster: alive
    new = S.apply_roster(s, [], "2026-10-01T20:00:30Z")
    assert s["sessions"]["kube-agents-vamp-1"]["roster_status"] is None and new == []
    # absent long after its last report: gone, but the report's status survives for the record
    new = S.apply_roster(s, [], T1)
    row = s["sessions"]["kube-agents-vamp-1"]
    assert row["roster_status"] == "gone" and row["status"] == "waiting-human"
    assert [i["kind"] for i in new] == ["orphan"]
    # it comes back: orphan clears, status still intact
    S.apply_roster(s, [{"name": "kube-agents-vamp-1", "status": "busy", "kind": "interactive", "started_at": T0}], T2)
    assert row["status"] == "waiting-human" and not any(i["kind"] == "orphan" for i in s["attention"])


def test_escalation_items_clear_when_their_cause_goes_away():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T0)
    for kind in ("stalled", "red", "threads"):
        S.add_attention(s, "kube-agents-vamp-1", kind, 5, "x", T0)
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: #5 round 1\nstatus: working\n"), T1)
    assert s["attention"] == []
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-2\nprs: #5 round 1\nstatus: working\n"), T1)
    assert [i["kind"] for i in s["attention"]] == ["ownership-conflict"]
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-1\nprs: none\nstatus: working\n"), T1)
    assert s["attention"] == []


def test_waiting_bnaylor_item_is_keyed_on_the_session_and_names_the_pr_in_the_question():
    s = S.empty_state()
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1935 round 6\nstatus: waiting-human: file an issue for #1938's leftovers?\n"), T0)
    assert new[0]["id"] == "kube-agents-vamp-20:waiting-human:-" and new[0]["pr"] == 1938
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-20\nprs: #1900 round 1; #1935 round 6\nstatus: waiting-human: file an issue for #1938's leftovers?\n"), T1)
    assert len(s["attention"]) == 1 and s["attention"][0]["notified"] is False and s["attention"][0]["since"] == T0


def test_save_state_is_atomic(tmp_path: Path):
    s = S.empty_state()
    S.save_state(s, tmp_path / "state.json")
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_roster_waiting_does_not_duplicate_an_open_waiting_bnaylor_item():
    s = S.empty_state()
    S.apply_report(s, report("OVERSEER REPORT kube-agents-vamp-f5\nprs: none\nstatus: waiting-human: design q\n"), T0)
    new = S.apply_roster(s, [{"name": "kube-agents-vamp-f5", "status": "waiting", "kind": "interactive", "started_at": T0}], T1)
    assert new == [] and [i["kind"] for i in s["attention"]] == ["waiting-human"]


def _at(minute):
    return f"2026-10-02T{16 + minute // 60}:{minute % 60:02d}:00Z"


def _live(*names):
    return [{"name": n, "status": "idle", "kind": "interactive", "started_at": _at(0)} for n in names]


def test_rename_replay_needs_no_human_once_the_new_name_claims_the_pr():
    # 2026-10-02: ws3 asked a question on #2245, was restarted as ws3-expressive-cocoa, which claimed #2245
    s = S.empty_state()
    old, new_name = "kube-agents-ws3", "kube-agents-ws3-cocoa"
    S.apply_roster(s, _live(old), _at(40))
    S.apply_report(s, report(f"OVERSEER REPORT {old}\nprs: #2245 round 2 1-threads\nstatus: waiting-human: approve plan for #2245?\n"), _at(47))
    new = S.apply_roster(s, _live(new_name), _at(52))
    assert s["sessions"][old]["roster_status"] == "gone"
    assert [i["kind"] for i in new] == ["orphan"]
    # the new name claims the PR while the old row still lists it: no conflict against a gone session
    new = S.apply_report(s, report(f"OVERSEER REPORT {new_name}\nprs: #2245 round 2 1-threads\nstatus: working\n"), _at(56))
    assert new == []
    assert s["prs"]["2245"]["owner"] == new_name
    assert [i["id"] for i in s["attention"]] == [f"{old}:waiting-human:-"]     # orphan gone: #2245 has an owner
    # inside the grace the old question stays; past it, it is swept
    S.apply_roster(s, _live(new_name), _at(61))
    assert [i["kind"] for i in s["attention"]] == ["waiting-human"]
    S.apply_roster(s, _live(new_name), _at(62))
    assert s["attention"] == []
    assert s["sessions"][old]["status"] == "waiting-human" and s["sessions"][old]["prs"] == [2245]   # the record stays


def test_conflict_between_live_sessions_clears_once_one_has_been_gone_the_grace():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: working\n"), _at(1))
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #5 round 1\nstatus: working\n"), _at(2))
    assert [i["kind"] for i in new] == ["ownership-conflict"]
    S.apply_roster(s, _live("kube-agents-b"), _at(10))
    assert [i["kind"] for i in s["attention"]] == ["ownership-conflict"]      # a blip does not settle it
    S.apply_roster(s, _live("kube-agents-b"), _at(20))
    assert s["attention"] == [] and s["prs"]["5"]["owner"] == "kube-agents-b"


def test_a_claim_made_during_a_blip_raises_the_conflict_when_the_owner_returns():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: working\n"), _at(1))
    S.apply_roster(s, _live("kube-agents-b"), _at(5))
    assert S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #5 round 1\nstatus: working\n"), _at(6)) == []
    new = S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(7))
    assert [i["id"] for i in new] == ["kube-agents-b:ownership-conflict:5"]


def test_a_gone_session_that_reports_is_live_before_the_watcher_sees_it():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: working\n"), _at(1))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #5 round 1\nstatus: working\n"), _at(2))
    S.clear_attention(s, "kube-agents-b:ownership-conflict:5")
    S.apply_roster(s, _live("kube-agents-a"), _at(5))
    S.apply_roster(s, _live("kube-agents-a"), _at(20))
    assert s["prs"]["5"]["owner"] == "kube-agents-a"             # b settled: #5 handed to a
    # b is resumed and reports before the next roster pass: its question and its claim stand
    new = S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #5 round 1\nstatus: waiting-human: merge #5?\n"), _at(30))
    assert sorted(i["kind"] for i in new) == ["ownership-conflict", "waiting-human"]
    assert sorted(i["kind"] for i in s["attention"]) == ["ownership-conflict", "waiting-human"]
    assert s["prs"]["5"]["owner"] == "kube-agents-b"
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(31))
    assert sorted(i["kind"] for i in s["attention"]) == ["ownership-conflict", "waiting-human"]


def test_a_gone_session_that_reported_once_and_vanished_again_is_swept_later():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a"), _at(0))
    S.apply_roster(s, [], _at(5))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: none\nstatus: waiting-human: q\n"), _at(30))
    S.apply_roster(s, [], _at(31))                               # report still fresh: alive
    assert [i["kind"] for i in s["attention"]] == ["waiting-human"]
    S.apply_roster(s, [], _at(33))                               # report aged: gone afresh
    assert s["sessions"]["kube-agents-a"]["gone_since"] == _at(33)
    S.apply_roster(s, [], _at(42))
    assert [i["kind"] for i in s["attention"]] == ["waiting-human"]
    S.apply_roster(s, [], _at(43))
    assert s["attention"] == []


def test_gone_owner_hands_its_pr_to_a_live_claimant_after_the_grace():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #5 round 1\nstatus: working\n"), _at(1))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: working\n"), _at(2))
    S.clear_attention(s, "kube-agents-a:ownership-conflict:5")
    new = S.apply_roster(s, _live("kube-agents-b"), _at(10))
    assert s["prs"]["5"]["owner"] == "kube-agents-a" and [i["kind"] for i in new] == ["orphan"]
    S.apply_roster(s, _live("kube-agents-b"), _at(20))
    assert s["prs"]["5"]["owner"] == "kube-agents-b" and s["attention"] == []


def test_a_pr_is_never_handed_to_another_gone_session():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a", "kube-agents-b"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-b\nprs: #1 round 1\nstatus: working\n"), _at(1))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #1 round 1\nstatus: working\n"), _at(2))
    S.apply_roster(s, _live("kube-agents-b"), _at(5))
    S.apply_roster(s, [], _at(10))
    S.apply_roster(s, [], _at(15))
    S.apply_roster(s, [], _at(25))
    assert s["prs"]["1"]["owner"] == "kube-agents-a"
    assert "kube-agents-a:orphan:1" in [i["id"] for i in s["attention"]]


def test_a_session_back_by_report_is_not_retired():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a"), T0)
    S.apply_roster(s, [], T1)
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: none\nstatus: waiting-human: q\n"), "2026-10-03T00:00:00Z")
    assert S.retire_due(s, "2026-10-03T00:00:30Z") == []
    assert [i["kind"] for i in s["attention"]] == ["waiting-human"]


def test_gone_session_with_no_successor_keeps_its_orphan_and_loses_its_question():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: waiting-human: merge #5?\n"), _at(1))
    S.apply_roster(s, [], _at(10))
    S.apply_roster(s, [], _at(30))
    assert [i["id"] for i in s["attention"]] == ["kube-agents-a:orphan:5"]
    assert s["prs"]["5"]["owner"] == "kube-agents-a"
    # merged: nothing is orphaned any more
    s["prs"]["5"]["state"] = "MERGED"
    S.apply_roster(s, [], _at(31))
    assert s["attention"] == []


def test_a_blip_shorter_than_the_grace_keeps_the_question():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: none\nstatus: waiting-human: q\n"), _at(1))
    S.apply_roster(s, [], _at(5))
    S.apply_roster(s, _live("kube-agents-a"), _at(9))
    S.apply_roster(s, _live("kube-agents-a"), _at(30))
    assert [i["kind"] for i in s["attention"]] == ["waiting-human"]


def test_sweep_leaves_hand_raised_items_alone():
    s = S.empty_state()
    S.apply_roster(s, _live("kube-agents-a"), _at(0))
    S.apply_report(s, report("OVERSEER REPORT kube-agents-a\nprs: #5 round 1\nstatus: working\n"), _at(1))
    S.add_attention(s, "-", "ownership-conflict", None, "#1970: two sessions planned it", _at(1))["manual"] = True
    S.add_attention(s, "kube-agents-a", "ownership-conflict", 5, "judgment call", _at(1))["manual"] = True
    S.add_attention(s, "kube-agents-a", "waiting-human", None, "asked in chat", _at(1))["manual"] = True
    S.apply_roster(s, [], _at(10))
    S.apply_roster(s, [], _at(40))
    ids = sorted(i["id"] for i in s["attention"])
    assert ids == ["-:ownership-conflict:-", "kube-agents-a:orphan:5", "kube-agents-a:ownership-conflict:5",
                   "kube-agents-a:waiting-human:-"]
