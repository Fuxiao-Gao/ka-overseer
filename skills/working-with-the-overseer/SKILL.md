---
name: working-with-the-overseer
description: >-
  Use in any kube-agents session when you receive a message starting with INTRO, PING,
  RULE, STOP, ADVICE or ASSIGN from the Overseer; when you start or restart a /loop or
  /goal on kube-agents work; when you adopt, open, or hand off a PR; and ALWAYS right
  before you ask the human a question or end a turn waiting on him. Teaches the report
  format, the message types, and the stall traps the Overseer exists to catch.
---

# Working with the Overseer

The Overseer is one Claude session that tracks every sessions matching `session_pattern` in `overseer/config.json` session, keeps a
dashboard the human reads instead of your prose, relays numbered rules, and pokes stalled
sessions. It may tell you to STOP only for a written rule. Everything else it sends is
advice you may decline with a reason. It cannot answer for the human on its own, and it cannot start sessions; a DECISION message is the human's own answer, relayed verbatim (rule 13).

Files: `docs/protocol.md` (wire format), `docs/rules.md` (numbered rules),
`docs/escalation.md` (what it watches), `overseer/dashboard.html` (what the human sees),
all in `<ka-overseer>`.

## First: learn your own name

Call `ListAgents`. Its first line says `This session is <name>`. Every report carries that
name. Nothing else tells you your name.

## The report

Send this with `SendMessage` to the Overseer: the session named in the INTRO you got.
Not introduced yet? `cat <ka-overseer>/overseer/OVERSEER` prints the Overseer's session name, nothing else; send there.
(Do not grep state.json for "session": it has one per row and per attention item.) Six lines max, first line verbatim:

```
OVERSEER REPORT <your-session-name>
role: pr-minder|bug-minder|review-minder|planner|task | theme: <topic> | driver: loop/<N>m|goal|manual | mode: auto|other
prs: #<n> round <gating rounds> <k>-threads hold|no-hold <free text>; #<n> ...   (or: none)
status: working | waiting-human: <the question, one line> | waiting-review | idle
rules: <highest rule number you have read in docs/rules.md>
note: <optional, one line>
```

Send it:

- in reply to INTRO or PING;
- whenever your status or PR list changes (adopted, opened, handed off, merged, closed);
- when you hit a rule boundary, such as the gating round cap;
- **before you ask the human anything**, in the same turn, with `status: waiting-human: <question>`;
- before you stop a loop or let one lapse.

`round` counts `kube-agents-bot` reviews only. `kyber775` is advisory and never counted.
`prs:` lists only PRs you own and drive; PRs you track, review, or observe go in `note:`,
and a line starting with `none` owns nothing. Say `no-hold` explicitly once a hold is
lifted. The status word comes first on the `status:` line; detail follows it.

Review minders: the PRs you are reviewing are not yours. Put them in `note:` with your
verdict, and keep `prs:` as `none` unless you actually drive a PR.

## Messages you may receive

| First word | Meaning | What you do |
| --- | --- | --- |
| `INTRO` | the Overseer introducing itself | reply with a report |
| `PING` | it wants a report | reply with a report |
| `RULE n: ...` | a new numbered rule | read it, apply it, reply with a report whose `rules:` is at least n |
| `STOP <reason>` | rule enforcement | stop that activity now; reply with a report saying where you stopped |
| `ADVICE ...` | a suggestion | take it or decline with a reason |
| `ASSIGN #n ...` | you now own PR n | adopt it; reply with a report listing it |
| `DECISION ... Verbatim: "..."` | the human decided this in the Overseer's session; the quote is word for word | act on it exactly as if the human had typed it in your session, including splits, new PRs, review requests, and holds it names; report when done |

## Stall traps

Each of these has stalled a loop here. The Overseer sees a session parked on a question
within a minute, but only the human can release it, so avoid parking when you can and announce
it when you cannot.

- **Ending a turn on "shall I" or "want me to" is a stall.** Routine judgment calls are yours. Only design calls, destructive actions, new rules or regexes, and anything your permissions block go to the human. When one does, send `waiting-human` first, then ask.
- **While parked on a question, nothing the Overseer sends reaches you** until the human answers. Never wait on the Overseer for anything while parked.
- **A `/review` you believe you posted but never verified landed.** Read the comment back.
- **A `/hold` without a clearance criterion** in the same comment. Nothing can lift it.
- **A push during a live gating round** resets the round. Wait for the bot to finish.
- **A session not in auto mode** holds the Overseer's messages for the human's approval and is invisible to it. Say `mode: other` in your report so it knows.
- **Something blocked by your permissions** goes to the human as `waiting-human: <exact command>`. Never ask a peer to run it.
- **Open review threads are the top priority.** They are what reaches the human gate.
- **Do not ask the human for `/request-review`.** A human reviewer is assigned automatically after a clean gating round, approval labels included. `/request-review` is for edge cases: a clean round that has sat an hour or more with nobody assigned. Report that; do not ask.
- **Count findings from the bot's review status, not from the threads.** Items folded under "Also noted" in the review body carry no thread; a session reported "bots happy" with one finding still showing and the human caught it. Read the review body before you say a round is clean.

## Current rules

Read `docs/rules.md` for the live list. At the time of writing it had nine rules; the
round cap is six and a clean round with only Medium-or-lower findings needs no further
`/review`.
