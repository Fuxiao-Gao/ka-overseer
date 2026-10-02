
15. A session minding a PR reads the bot's review summary body and the top-level PR comments, not only the resolvable threads. kube-agents-bot raises its PR-description finding in the review body, which has no thread, so a thread-only scan reports a round clean while the finding stands. Count findings from the review status; a body-only fix needs /review fresh, not /review.
