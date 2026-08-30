---
status: draft
created: 2026-08-29
updated: 2026-08-29
agent_value: 3
key_files: [cli/agents.py, cli/rollcall.py, cli/canvas/catalog.py]
---

# Agent sessions — who is running right now

## Why

Several Claude Code sessions run side by side across the sibling repos, each holding a working
tree and each burning a context window nobody can see the bottom of. `ps` finds the processes and
can tell you nothing about them: not which repo, not whether the session is working or waiting,
not when it started, not what it is called.

**This is the tower's subject arriving early, and from outside.** The tower's `IN FLIGHT` band was
drawn for jobs sky.boss started; the jobs the operator actually wants to watch are the ones it did
not. That inversion is the whole reason this is buildable now — sky.boss watching what other tools
do is what sky.boss is, and it needs none of the four primitives the tower is otherwise blocked on.

**And it partly supplies one of them.** *Job identity that outlives a window* (`docs/open.md` item
6) is what the plan and the tower are waiting for, and a session registry hands over most of it for
free: a stable `sessionId`, a derived `name`, and a start time that survives every window sky.boss
ever drew. It does **not** close item 6 — sky.boss's own runs are still anonymous, which is the
harder half — but it means the band can have real rows in it first.

## Shape

**A command the surfaces render, not a panel with a reader inside it.** The surface is a consumer
of the envelope and never a second CLI ([[canvas]]), so this is `sb` returning a `Result` that the
tower draws. Its shape is already in the tree: [[roll-call]] asks every declared project how it is
and folds the answers; this asks every provider who is running and folds the answers. Same fold,
different population.

**Not named `fleet`.** That word is breeze.brain's rental fleet and the collision has already cost
clarity once.

### The adapter seam

**One interface, one adapter, and no speculative second.** The operator's ask is that this not be
Anthropic-shaped in its bones, and the honest position is that exactly one registry has been read.
So the seam is decided now and a second provider is a day of reading rather than a refactor.

An adapter answers one question — *what agent sessions are live* — and returns records in one
vocabulary:

```
provider  id  name  cwd  status  started  pid
```

**Thin, and nothing else** (ruled 2026-08-29). A provider that knows more — context used, model,
token spend, the branch a session sits on — has that dropped rather than half-rendered. The
alternative was a per-provider extras bag, which is useful and is also how a common vocabulary
rots: the first consumer that reads `extras.context` has made it part of the contract without
anyone deciding to. The tower must be able to draw a row from an adapter it has never heard of
without special-casing it, or the modularity was decorative — and that is only true if there is
nothing provider-shaped in a row to special-case.

**An adapter that finds nothing is silent, never an error.** Nobody has five agent CLIs installed
at once, so *not present* is the common case and must print nothing at all. Same rule an absent
`$SB_HOME` already lives under.

**The provider rides on every row**, because a fold that shows five rows without saying which are
whose is worse than one that shows four.

### The Claude adapter

Verified on this machine rather than assumed. `~/.claude/sessions/` holds one JSON file per live
session, `<pid>.json`, written by the session itself, carrying `sessionId`, `cwd`, `name`,
`status` (`busy` / `idle`), `kind`, `entrypoint`, `startedAt`, `version`, `procStart`, and a
messaging socket path.

**Liveness is two fields, not one.** A record outlives the process that wrote it, so a `pid` alone
lies twice — once for a crashed session whose file is still there, once for a PID the kernel has
recycled onto something else. The record pins `procStart` (field 22 of `/proc/<pid>/stat`) for
exactly this, and a row is live only when both agree. A reader that trusts the PID reports dead
sessions as running, which is *worked fine, told nobody* in its most confident form.

**It is an internal format with no contract.** Undocumented, versioned per record, free to change
under a client update. So an absent, renamed or unparseable registry degrades to *nothing declared*
and never to a raised error — and never to an empty band that reads as *nothing is running*, which
is the same lie in the other direction.

**Does not do:**

- **No management.** Not starting sessions, not stopping them, not routing work between them.
  `messagingSocketPath` is a live socket into another agent's session and a stop button would put a
  *write* into a panel built as an observe. Not forbidden forever — [[fundamentals]] would have to
  say so on purpose, the way the clock-source selector crosses the daemon line on purpose — but out
  here.
- **No transcripts.** An agent's transcript is the operator's conversation, and a panel that
  surfaced it would put someone else's prompts onto a canvas that also has an [[mcp]] surface. The
  band shows that a session exists, where, and whether it is working.
- **No extras bag**, per the ruling above. Reopen it as a round when a second adapter exists to
  argue with, not before.
- **No history.** This is *now*, like every other observe here. What ran yesterday is
  `docs/open.md` item 5 and a different question.
- **No speculative adapters.** A provider whose on-disk state nobody here has opened does not get
  a module written against a guess.

## Phases

### Round 1 — the fold, and one adapter (2026-08-29)

- [ ] `cli/agents.py`: the record dataclass, the adapter protocol, and the fold. Pure enough that
      the fold is testable without a registry on disk.
- [ ] The Claude adapter, reading `~/.claude/sessions/*.json`, with liveness on **both** `pid` and
      `procStart` and a test that a stale record with a live recycled PID is not reported.
- [ ] Every degrade path silent: absent directory, unreadable file, unparseable JSON, a record
      missing a field. Each named in `warnings`, none raising, and none producing an empty success.
- [ ] `sb agents` returns the envelope, ordered — probably by `started`, oldest first, so the
      session that has been going longest is at the top.
- [ ] `--only NAMES`, matching [[roll-call]]'s flag rather than inventing a second spelling.

### Round 2 — where the adapter list lives (not scheduled)

The one genuinely open half. Parsing a format is code, so adapters are modules in `cli/`; but
*which are enabled* looks like operator content, and `projects.toml` is the precedent — outside the
repo, never written by sky.boss. Splitting it that way means shipping code for a provider the
operator has turned off, which is fine, and lets a machine with nothing installed stay silent with
no config file existing at all. Round 1 ships one adapter and does not need the answer.

### Round 3 — the band (not scheduled)

The tower does not exist. When it does, this is a consumer of the envelope round 1 returns.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-29)

Lifted from `docs/open.md` items 16 and 17, which had accumulated enough measured detail to be a
spec rather than a question. The two rulings taken on the day it was written:

**The record is thin.** Chosen over an extras bag on the argument that a common vocabulary with an
escape hatch is a common vocabulary that will not survive its second provider. The cost is real and
worth stating: `status: busy` is Claude's word and the interface keeps it, so the vocabulary is
already one provider's shape in at least one field. That is a debt, not a refutation — the fix if a
second adapter disagrees is to widen the *enum*, which is a decision, rather than to widen the
*record*, which is a hole.

**Item 6 is partly supplied and not closed.** Worth keeping the distinction visible: the registry
gives identity to sessions sky.boss did not start. Everything sky.boss runs itself is still
anonymous and dies with its window, and no amount of reading someone else's registry fixes that.
