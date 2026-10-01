# Problem

I am running a lot of parallel claude sessions working on lots of different PRs in kube-agents.
Claude behavior lately (esp. Opus 5.5, Fable 5.1) seems to tend towards pausing to ask me questions
but in a way that it takes me some time to notice.  Work stalls during these, and often the /loops
and /goals get blocked as a result.

I also experience a decent amount of cognitive load trying to keep track of the status of all
of these sessions, the PR needs, which session is doing what, etc.  Verbosity of claude output is 
also a challenge under pressure.

I have used some informal coordination sessions in the past with some success.  I'd like to
formalize that and uplevel it.

# Inter-session communications

Claude-code has ~recently added intersession communications and this has been a lifesaver of
a feature.  I'm making a lot of use of this lately, and it strikes me that we can do even
better.

# The Overseer

A new session will become the Overseer.  It's job is to know what all the other sessions are 
doing, what their statuses are, relay that information to me, and poke and prod them when
they get stuck.  To relay new rule/process changes to them, and make suggestions for how to
unblock things.

In bullet form:

- Introduce yourself to the open sessions, or new sessions that appear.  Explain your role.
- Keep a running table of kube-agents sessions and their tasks, the general theme of the work
  they're doing (I try to keep it topically related within a session for contextual purposes.  
  Eg, chat backends, authority, UI, etc.)
  - Are they being driven by specific instructions, a /loop, or a /goal?
    - Typically I have already some roles defined:
      - PR Minder (PRs that I own that are not assigned to any specific session)
      - Bug Minder (Bugs that are assigned to me and are not being worked)
      - Review Minder (When another teammate asks me for a review on a PR)
      - General task-focused session - there are usually 4 or 5 of these.
  - PRs being worked
  - Status of those PRs
  - Time of last activity
  - Time of last update
  - Number of bot review rounds
- Produce an html dashboard that I can use to track status more easily than reading lots
  of varied prose.  Update this whenever anything changes.  This can be a static file, or
  some little python server or something if we need more interactivity.
- Periodically check on the PRs independently to see their state, and if the owning session
  is keeping up with the status.
- Proactively advise off-track sessions on how to proceed to unblock the PRs
- Assign new work to the sessions when I ask to retarget or distribute new work.

General direction:
- We have an occasional issue where nit-pick reviews will cause out-of-control spirals
  where the PR grows without bound, the reviews never converge, and the code goes off
  in some non-core direction.  Twice this has happened with suggestions to improve unit
  tests or safety features that involve regular expressions.  Each round uncovers new
  things.  These rounds need to be capped at some reasonable level (6,7) and re-evaluated
  for drift.
- A new rule in kube-agents that is evolving, related to the last point, is that if you
  resove a bot review that had Medium or below findings, you do not need to do ANOTHER
  /review after fixing those.  You can proceed to human review.
- Resolving open comment threads is a priority because this is what gets us to the human gate.



