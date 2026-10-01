# overseer/tests/test_gh_snapshot.py
import json
from pathlib import Path

import gh_snapshot as G
import state as S

FIX = json.loads((Path(__file__).parent / "fixtures" / "pr2077.json").read_text())
T0 = "2026-10-01T20:00:00Z"


def test_checks_state():
    assert G.checks_state([]) == "none"
    assert G.checks_state([{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]) == "green"
    assert G.checks_state([{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"},
                           {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": None}]) == "red"
    assert G.checks_state([{"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": None}]) == "pending"
    assert G.checks_state([{"__typename": "StatusContext", "state": "SUCCESS"}]) == "green"
    assert G.checks_state([{"__typename": "StatusContext", "state": "PENDING"}]) == "pending"
    assert G.checks_state([{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},
                           {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "NEUTRAL"}]) == "green"


def test_classify_real_pr():
    row = G.classify_pr(FIX, unresolved=0)
    assert row["title"].startswith("fix(operator)")
    assert row["head"] == FIX["headRefOid"][:8]
    assert row["branch"] == "fix/tasks-budget-reads-bridge-concurrency"
    assert row["rounds"] == sum(1 for r in FIX["reviews"] if r["author"]["login"] == "kube-agents-bot")
    assert row["advisory_rounds"] == sum(1 for r in FIX["reviews"] if r["author"]["login"] == "kyber775")
    assert row["approved"] is True and row["lgtm"] is False and row["hold"] is False
    assert row["reviewers"] == ["jayantid"]
    assert row["unresolved_threads"] == 0
    assert row["checks"] == "green"
    assert row["state"] == "OPEN" and row["draft"] is False
    assert row["last_activity"] == FIX["updatedAt"]


def test_labels_drive_hold_lgtm_approved():
    pr = dict(FIX, labels=[{"name": "lgtm"}, {"name": "do-not-merge/hold"}])
    row = G.classify_pr(pr, 0)
    assert row["lgtm"] is True and row["hold"] is True and row["approved"] is False


def test_compute_drift():
    assert G.compute_drift({"rounds": 5, "unresolved_threads": 0, "hold": False, "owner_belief": None}) is None
    assert G.compute_drift({"rounds": 5, "unresolved_threads": 0, "hold": False,
                            "owner_belief": {"rounds": 5, "threads": 0, "hold": False}}) is None
    d = G.compute_drift({"rounds": 6, "unresolved_threads": 2, "hold": False,
                         "owner_belief": {"rounds": 5, "threads": 0, "hold": None}})
    assert "rounds 5" in d and "GitHub 6" in d and "threads 0" in d and "GitHub 2" in d
    assert G.compute_drift({"rounds": 6, "unresolved_threads": 2, "hold": True,
                            "owner_belief": {"rounds": None, "threads": None, "hold": False}}) == "owner says no hold, GitHub has hold"


def test_snapshot_merges_and_survives_a_failed_fetch():
    s = S.empty_state()
    S.pr(s, 2077)["owner"] = "kube-agents-vamp-54"
    S.pr(s, 2077)["owner_belief"] = {"rounds": 5, "threads": 0, "hold": False}
    S.pr(s, 9999)["title"] = "old title"

    def fetch_pr(n):
        if n == 9999:
            raise RuntimeError("HTTP 502")
        return FIX

    result = G.snapshot(s, {2077, 9999}, fetch_pr, lambda n: 0, T0)
    assert result["updated"] == [2077] and list(result["errors"]) == [9999]
    assert s["prs"]["2077"]["owner"] == "kube-agents-vamp-54"
    assert s["prs"]["2077"]["rounds"] == G.classify_pr(FIX, 0)["rounds"]
    assert s["prs"]["2077"]["snapshot_error"] is None
    assert s["prs"]["9999"]["title"] == "old title"
    assert s["prs"]["9999"]["snapshot_error"] == "HTTP 502"
    d = s["prs"]["2077"]["drift"]
    assert d is None if s["prs"]["2077"]["rounds"] == 5 else "GitHub" in d


def test_scope_numbers_unions_lists_and_state():
    s = S.empty_state()
    S.pr(s, 5)
    cmds = {"prs": lambda: [5, 6], "reviews": lambda: [7], "reviewed": lambda: []}
    assert G.scope_numbers(s, cmds) == {5, 6, 7}


def test_tide_context_is_merge_pool_state_not_a_check():
    assert G.checks_state([{"__typename": "StatusContext", "context": "tide", "state": "PENDING"},
                           {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]) == "green"
    assert G.checks_state([{"__typename": "StatusContext", "context": "tide", "state": "PENDING"}]) == "none"


def test_snapshot_keeps_previous_rounds_for_delta_detection():
    s = S.empty_state()
    G.snapshot(s, {2077}, lambda n: FIX, lambda n: 0, T0)
    assert s["prs"]["2077"]["rounds_prev"] is None
    G.snapshot(s, {2077}, lambda n: FIX, lambda n: 0, T0)
    assert s["prs"]["2077"]["rounds_prev"] == s["prs"]["2077"]["rounds"]


def test_fetch_unresolved_paginates_past_100_threads():
    pages = [
        {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": True}] * 99 + [{"isResolved": False}],
                                                                   "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}}}},
        {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [{"isResolved": False}, {"isResolved": False}],
                                                                   "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}},
    ]
    seen = []
    def graphql(variables):
        seen.append(variables.get("after"))
        return pages.pop(0)
    assert G.fetch_unresolved(2056, graphql=graphql) == 3
    assert seen == [None, "c1"]
