# Overseer escalation

Proactive path: the skill makes sessions self-report `waiting-human` before they ask.
That creates an attention item immediately, with one notification.

Signals checked each tick for sessions that have not self-reported:

| Signal | Threshold | Action |
| --- | --- | --- |
| Roster `waiting` (parked on a question or prompt) | immediate, by `watch.sh` | attention item, one notification; Overseer adds the PR context on its next tick |
| Silent while an owned PR moved | past 2x stated cadence | PING with idle subscription, ladder 1 |
| Roster idle but last report said working | one tick | PING, ladder 1 |
| Gone from roster while owning open PRs | immediate | attention item "orphan", offer reassignment |
| Unresolved threads untouched, owner silent | 2 h | PING; attention after one more tick |
| Red check | 1 h | PING; attention after one more tick |
| Parked waiting-review, no reviewer assigned | 1 day | ADVICE (request review); attention after one more tick |
| Gating rounds | 6 or more | STOP, attention item "drift check" |

Ladder for a non-reporting session: PING with an idle subscription (1) → next tick PING
again (2) → attention item and one notification (3). The idle notice carries a summary of the
session's last turn, so a session that forgets to report still tells the Overseer what it did. The ladder resets on any
report. An attention item notifies once and persists until the session reports a different
status, the facts overtake it (below), or the human clears it. No repeat notifications for the same item.

Facts that clear an item without a report, checked after every report and roster pass. A
restart or rename leaves the old name gone while the new name carries on, and these keep
its leftovers off the band:

- A session that reports after leaving the roster counts as back, before the watcher sees it.
- No ownership conflict is raised against a gone owner. If that owner returns still listing
  the PR, the conflict is raised then. A conflict clears once at most one session lists the
  PR, not counting sessions gone 10 minutes.
- An orphan clears once the gone session owns no open PR (another session claimed it, or it merged or closed).
- A session gone 10 minutes loses its `waiting-human` item, and each PR it owns passes to
  a live session that lists it. With no such session, the orphan stays.
- A session that reported after leaving is not retired on the strength of the old departure.
- Items opened by hand with `ovsr.py attention` are marked manual and never swept by these
  rules. The older clears still apply to them: a different reported status clears
  `waiting-human`, and retire drops everything the session had.

Notification: `osascript -e 'display notification "<session>: <what>" with title "Overseer"'`.

## Attention item ids

`<session>:<kind>:<pr or ->` where kind is one of `waiting-human`, `waiting`,
`orphan`, `drift-check`, `stalled`, `red`, `threads`, `no-reviewer`,
`ownership-conflict`. An id notifies once. The same id reopened after being cleared
notifies again.
