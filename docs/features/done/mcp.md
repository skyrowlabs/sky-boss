---
status: complete
created: 2026-08-22
updated: 2026-08-23
agent_value: 3
key_files:
  - cli/mcp.py
  - cli/canvas/catalog.py
  - cli/tools.py
  - cli/output.py
  - tests/test_mcp.py
---

# The MCP surface — the tools, offered to an agent

## Why

The ideas list asks, of chaining sb into an agent: *"how different is this from the tools we
have?"* Honestly answered: **barely, and the arrow is pointing the wrong way.**

`sb run -- claude -p "…"` already works. `sb follow -- claude -p "…"` already works and gives
you a ring, a liveness clock and a dead state. Feeding sb's output *into* an agent is
`sb --json data -- jam pr list --json | claude -p "…"`, which is a shell pipe, and `tools.toml`
bans pipes on purpose — a pipeline tool would reintroduce a mini-language for something bash
already does. There is no feature in that direction worth building.

**The direction with value is the inverse: let the agent call sb.** Today an agent that wants to
know the state of something has to know the tool, its flags, its working-directory quirk, and
how to parse what it prints. The operator solved all four already — once, for themselves, in
`tools.toml`. `sb tools jam-pr-list` is a name that means *"open PRs, with the merge column
GitHub cannot show, from the right directory, as data."* That is exactly the shape MCP exists to
carry, and sb is already holding it.

**Two things this repo built for other reasons make the surface nearly free:**

1. **`catalog.walk()` already generates a tool list from the live Click tree**, because the
   canvas needed a palette that could not drift. It already carries a name, a summary, and the
   three properties that decide exposure: `acts`, `resident`, `saved`. An MCP `tools/list` is
   that catalog with a different serialisation. *Nothing keeps a command table* pays for itself
   a second time.
2. **`--json` purity is already a tested invariant.** Over stdio, the MCP protocol *is* stdout —
   so the rule that keeps `sb --json … | jq` parseable is the same rule that keeps the protocol
   intact. The surface inherits a guarantee instead of asking for one.

## Shape

    sb mcp

Speaks MCP on stdin/stdout. The client spawns it; the client owns the pipe.

### The tools are the surface, and this is the whole safety argument

**Exposing `data` or `read` would convert an operator's assertion into an agent's guess.** The
act/observe split rests on one sentence: *sb cannot tell a read from a write by inspecting an
argv and does not try — choosing `data` over `run` is the operator's assertion that this one is
a read.* That works because the operator typed it. An MCP tool called `data` taking a free-form
argv would let the **agent** make that assertion, about an argv nobody reviewed, and an
assertion nobody validated is not a safety property. It is a shell with a reassuring name.

So the surface is **what takes nothing from its caller** — every saved command, since each is an
argv the operator wrote down with `acts` inherited from its first word, plus any builtin that reads
only operator-declared content and accepts no argv.

*Amended during round 1 (2026-08-23): this read "saved commands only". [[roll-call]] did not exist
when it was written, and it satisfies every reason the rule was given — its sources are declared in
`projects.toml`, it takes no argv, it does not act and it is not resident — while failing the rule
as literally spelled. The exclusions below already argued builtins out on two grounds, "`sb tools`
is a listing" and "the argv-takers are excluded above", and neither covers it: that was a gap, not
a decision. A builtin opts in with `sb_mcp` on the command object, read off the tree like
`sb_surface` and `sb_acts`, so no name is written down in a module. See Notes.* `tools.toml` becomes the allowlist without anyone
inventing an allowlist, which is the same move [[tools]] made for the canvas sidebar.

**And a saved command takes no arguments.** That is a rule [[tools]] round 1 wrote for a
different reason — *a tool that took arguments would be a shell function, and this is not a
shell* — and it lands here as something much stronger: **every exposed tool has an empty input
schema.** There is no string an agent can put anywhere. The injection surface is not small, it
is absent.

Three exclusions follow from properties that already exist, read off the catalog rather than
written into a list:

- **`acts` → excluded.** A saved command wrapping `run` never appears. Acting stays the
  operator's, and an agent that needs something done asks them.
- **`resident` → excluded.** A stream has no single response, which is why `sb follow` already
  refuses `--json`; a request/response protocol is the same shape of problem and gets the same
  answer.
- **sb's own commands → excluded.** `sb tools` is a listing, and MCP lists tools natively; the
  argv-takers are excluded above. `sb mcp` excludes itself with `sb_surface`, exactly as
  `sb ui` does.

### stdio, not a port

The canvas server is remote code execution bound to a port and is treated that way — loopback,
a required custom header, a per-launch token, an `Origin` check, no CORS. **A second port would
be a second thing to defend, and it would be defending the same commands.** Over stdio there is
no port, no token, no origin: the client spawned the process and holds both ends of the pipe.
The entire threat model collapses into "who may spawn `sb mcp`", which the operating system
already answers.

### What comes back

The envelope, as JSON text — `ok`, `partial`, `data`, `warnings`, and `view` where the command
set one. A failed command returns its envelope with `ok: false` rather than a protocol error: an
agent asking "what is the state of X" is owed "the tool failed and here is what it said" as an
*answer*, not as a transport fault.

**Bounded, for the third time.** A 120k-line result kills an agent's context as dead as it
killed a browser tab and a `RichLog` before it. The caps `read` and the canvas already apply are
the same caps here, for the same reason.

### Credentials

Unchanged, and this is why the boundary above matters. **sb is never in the credential path** —
external CLIs keep their own authentication, which CLAUDE.md names as the thing that *keeps a
future MCP surface safe to expose*. A saved command runs through `child_env()` with the
operator's environment, so `prs` returns GitHub data because `gh` is authenticated. The agent
therefore inherits the operator's reach for exactly the commands the operator curated — which is
the intended trade, stated plainly rather than discovered.

**Does not do:**

- **No port, no HTTP, no SSE.** stdio only. If a networked transport is ever wanted it is a
  round with its own security argument, not a flag.
- **No arbitrary argv, from anyone.** `run`, `read`, `data` and `follow` are not callable tools.
- **No acting.** Not `run`, not a saved command wrapping it, not with a confirmation prompt —
  MCP has no confirmation, the *client* does, and depending on someone else's UI for a safety
  property is not a safety property.
- **No writes.** `--save` lives on argv-taking commands, which are not exposed; nothing here
  writes `tools.toml`, for the reason [[tools]] rule 4 gives about surfaces.
- **No resources or prompts** in round 1. Tools only.
- **No second description language.** What the agent reads is the `description` the operator
  wrote in `tools.toml`, already used as `short_help` and already shown in `sb tools`. One
  string, three readers.

## Phases

### Round 1 — tools/list and tools/call over stdio (2026-08-22)

- [x] **The protocol subset, hand-rolled.** `initialize`, `notifications/initialized`,
      `tools/list`, `tools/call`, and a proper JSON-RPC error for anything else. No new
      dependency: the official SDK brings pydantic into a project that has deliberately avoided
      it, to save perhaps a hundred lines of JSON-RPC over a pipe. Revisit if the surface ever
      grows resources and prompts.
- [x] **The tool list is the catalog, filtered.** Saved, not acting, not resident — read off
      `catalog.walk()`, never a list of names. A test asserts a saved command wrapping `run`
      never appears, and that adding one to `tools.toml` makes it appear with no code change.
- [x] **`tools/call` runs it through the existing runner**, `child_env()` and all, and returns
      the envelope as JSON text. Failure is an envelope, not a fault. Results are capped.
- [x] **stdout carries protocol and nothing else.** The purity rule sb already tests, applied to
      a new consumer: a warning goes to stderr, a band goes to stderr, and a stray `print` is a
      corrupted session rather than an ugly one.
- [x] **`sb mcp` registers as a surface** — `sb_surface = True`, so it stays out of the palette
      and out of its own tool list.
- [x] **Help is the doc**, including the sentence that says what an agent may and may not reach
      and where the boundary is written down.

## Notes

### Round 1 — shipped, and the boundary moved one word (2026-08-23)

The design survived contact. What changed is the *spelling* of the rule, and the spelling turned
out to matter.

**"Saved commands only" was a category where the argument was a property.** [[roll-call]] landed
the same day this was built, and it satisfies every reason the rule was given — its sources are
declared in `projects.toml`, it takes no argv from its caller, it does not act, it is not resident
— while failing the rule as written. Reading the exclusions back settled it: builtins were argued
out on two grounds, *"`sb tools` is a listing"* and *"the argv-takers are excluded above"*, and
neither covers a builtin that takes nothing. That was a gap, not a decision.

So the rule is now **takes nothing from its caller**, which is what the safety argument was always
about, and a builtin opts in with `sb_mcp` on the command object — read off the tree exactly as
`sb_surface` and `sb_acts` are, so still no name written down in a module. Worth noticing the
shape: a boundary stated as a *list of what qualifies* went stale in one day, and the same boundary
stated as a *property* would not have.

**`capture` turned out to do both jobs this needed.** It keeps the envelope, so `tools/call` is not
a second trip through `--json` and back — [[refresh]] built that for an unrelated reason. And it
redirects `sys.stdout`, which over stdio *is the protocol stream*, so a command that printed would
corrupt the session rather than merely look untidy. `serve` takes its reference to the real stdout
before any of that, which is what keeps the swap from reaching the transport. Tested with a tool
that deliberately writes to both streams.

**Three exclusion tests were written before anything worked**, and that ordering was deliberate:
a surface offering one command too many would work perfectly and be wrong, which is the failure
this repo keeps finding by pointing things at reality. Here the reality is an agent, so the test
had to stand in for it.

**The measured result**, against real declarations: an agent calls one tool with no arguments and
gets 29 jam.sense jobs, a decisions ledger read from a file, and a named failure for a project that
has published nothing — `ok: true`, `partial: true`, one warning. That is the thing this whole
sequence was for, and it took no argument at all.

### Round 1 — drafted, awaiting the word (2026-08-22)

Scoped from the ideas list's own parenthetical — *how different is this from the tools we have?*
— and the honest answer to that question is what produced the design. Chaining needs nothing;
exposure needs a boundary. Writing the boundary down is the entire feature.

**The finding worth keeping is that the act/observe split does not survive a change of caller.**
It is not a property of an argv, it is a property of *who typed the argv*: `data` means "the
operator asserts this is a read". Hand that door to an agent and the assertion is being made by
the thing the assertion was protecting against. That single sentence rules out the obvious
design — one MCP tool per sb command — and points at the tools, where every argv already has
a human behind it.

**Two rules written for unrelated reasons turned out to be load-bearing here**, which is usually
the sign a design is in the right place. A saved command takes no arguments, so the input schema
is empty and there is nothing to inject. And nothing keeps a command table, so the tool list is
generated from the live tree and cannot offer an agent something that does not exist.

**It is worth saying what makes this worth building *now* rather than earlier.** The surface is
only as useful as the tools are many, and until [[tools]] round 3 filling them meant
opening `$EDITOR` and retyping an argv. `--save` made curation cost one flag at the moment the
command already worked. This round is what that curation is *for* — the tools stop being a
convenience for the operator and becomes the interface an agent is allowed to see.
