# Product principles

Direction set by the operator on 2026-11-01, after the first live
install: **borrow dsh-superagent's ideas, but build a Hermes product —
finish the last mile, design for user experience, do not ship a
pure-geek tool.**

These principles outrank feature work. When a design choice conflicts
with one of them, the principle wins and the feature gets re-thought.

1. **Borrow mechanisms, never habitats.** The Gate, Mandate and Report
   discipline are welcome imports. GitHub-issues-as-the-entry-point
   and repo-scoped memory are dsh's habitat, not Hermes'. Every
   borrowed idea is re-thought in Hermes' habitat: chat is the entry,
   the Kanban board is the durable record, profiles are the actors,
   the user's existing channels are where results return.
2. **The last mile is the product.** A capability is not done when it
   works from a terminal. It is done when all four hold: a task can be
   handed over in the chat the user already lives in; progress is
   visible without running a command; completion arrives unasked; the
   result is still findable next week.
3. **Humans get sentences, machines get enums.** Structured report
   kinds exist for the Watchdog. People get prose summaries, in the
   conversation, in their own language.
4. **No state a human needs may be CLI-only.** If the only way to see
   something is `sqlite3` or `grep` on a log, that is a bug, not a
   workflow. The dashboard is the viewing surface; the CLI is the
   fallback, not the interface.
5. **Configuration must survive being a user.** It must never live
   somewhere a `git pull` can eat it, never require editing a rendered
   file, and every error must arrive as a sentence with the fix
   attached — not a log tail to decode.
6. **Proactive beats queryable.** When the system knows something the
   user is waiting for, it says so. Polling is the system's job, not
   the user's.

## Last-mile backlog (honest status at v0.2.2)

| Item | Status |
|---|---|
| Chat-native entry (Feishu) so tasks start in conversation | Not yet — CLI only |
| Completion wakes the Router, which reports back in that chat (kanban subscription) | Not yet — impossible from a bare CLI session by design; arrives with the chat entry |
| Completion → global memory: terminal cards' summaries land in a suite journal / Router memory, recallable in later conversations | Not yet |
| User config lives outside the repo tree (source of truth under `~/.hermes/superagent/`), so upgrades cannot clobber it | Not yet — happened once in the field, 2026-11-01 |
| Guided setup as the default path; install errors in prose | Partial — SETUP.md exists |
| Dashboard-first status surfaces | Partial — Hermes' dashboard works; the suite does not point at it yet |
