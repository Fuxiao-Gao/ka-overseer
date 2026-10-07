You are evaluating whether the review loop on {repo} PR #{pr} has spiralled.
The PR has passed {rounds} gating bot-review rounds (the cap is {cap}), so its owner has been told
to stop fixing. A human ({human}) will read your report and decide what happens
next. You are read-only: do not comment, push, label, resolve threads, or post /review.

## Gather (gh CLI, git; repo {repo})

- The PR body as opened versus now, and its linked issue: what was this PR *for*?
  (`gh pr view {pr} -R {repo} --json title,body,closingIssuesReferences,commits,reviews,createdAt,additions,deletions`)
- Every bot review in order (author {gating_bot}, plus the `AI Review` check), with its
  findings: threads (`gh api graphql` on reviewThreads, including resolved ones) **and** the
  review body. Low findings are often folded into the body with no thread.
- The commits between rounds, and what each fix commit changed.
- Human comments, and any decision the human recorded (they may decide on the PR or in a session;
  commits or replies citing the human by name count).

## Classify each round

For every gating round, record: date, head SHA, finding count by severity, and for each
finding one of:
- **original**: about code or behaviour the PR set out to change;
- **fix-of-fix**: about code an earlier round's fix introduced or reshaped;
- **scope growth**: about something the PR did not originally touch;
- **description-only**: about the PR body, live-run evidence, or docs;
- **decided**: answered by an explicit human decision (cite it).

Also note: design pivots made inside the loop without a recorded human decision; growth in
diff size or number of files from first to last round; whether finding counts are falling
toward zero or plateauing above it.

## Report (markdown, under ~60 lines)

1. The first line must be exactly one of:
   `VERDICT: CONVERGED`, `VERDICT: CONVERGING`, `VERDICT: SPIRALLING`, `VERDICT: STALLED-ON-HUMAN`.
   CONVERGED means the last round has no findings above low, or every open finding is
   description-only or decided.
2. **Original intent**, in one sentence, and whether the PR still does only that.
3. **Round table**: round, SHA, High/Medium/Low counts, dominant class.
4. **Convergence point**: the round after which the code was substantially right and later
   rounds only polished, reacted to their own fixes, or wandered. Say "none" if it never
   converged, and why.
5. **Drift**: the scope growth and fix-of-fix findings worth naming, and any unrecorded pivots.
6. **Open now**: what is actually unresolved, and whose call each item is (author, the human,
   reviewer).
7. **Recommendation**: one of release (one more round is fine) / merge as is with a note /
   trim (name the commits or changes to revert) / split (name the pieces) / stop and redesign.
   Give the concrete next step and who takes it.

Be specific: cite SHAs, thread or review links, and file paths. Do not re-review the code
yourself beyond what you need to classify the findings.
