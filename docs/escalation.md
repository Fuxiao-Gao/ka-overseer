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
status or the human clears it. No repeat notifications for the same item.

Notification: `osascript -e 'display notification "<session>: <what>" with title "Overseer"'`.

## Attention item ids

`<session>:<kind>:<pr or ->` where kind is one of `waiting-human`, `waiting`,
`orphan`, `drift-check`, `stalled`, `red`, `threads`, `no-reviewer`,
`ownership-conflict`. An id notifies once. The same id reopened after being cleared
notifies again.
