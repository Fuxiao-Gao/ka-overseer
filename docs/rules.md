# Overseer rules

Numbered, stable. Changes append. A changed rule gets a new number and the old one is
struck through. Sessions acknowledge by sending `rules: N` in a report.

## Rules

1. Gating bot (`kube-agents-bot`) rounds cap at six. At the cap, stop fixing and re-evaluate for drift; new findings past the cap are the human's call.
2. A clean gating round whose findings were all Medium or below needs no further `/review`. Proceed to human review.
3. Resolving open review threads is the top priority. They are what reaches the human gate.
4. A `/hold` needs its reason and its clearance criterion in the same comment.
5. Never push while a gating review round is in flight.
6. Never lgtm the human's own PRs.
7. `kyber775` is advisory. It does not gate and its findings do not count as rounds.
8. A finding whose fix is a new rule, a regex, or a design change goes to the human, not into the PR.
9. Nothing blocked in your session is asked of a peer. Route it to the human via the Overseer.
10. Bot re-reviews (any review of a PR after its first) hold the check on High only. Medium findings are still posted as threads with their fix and counted in the title ("Found N issues, none holding"), but the check goes green with them open. The first review of a PR is unchanged: High and Medium both hold.
11. A Medium on a re-review is your call: fix it, or reply and resolve the thread. No further /review round is needed to get green. Threads must still be resolved before merge where the repo requires conversation resolution; the change removes the review loop, not the conversation.
12. Two things reset a PR to the first-review bar: a diff that has more than doubled since the last reviewed commit, or a /review on a commit that was already reviewed (that re-cuts the earlier review).
