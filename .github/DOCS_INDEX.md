# Documentation Index — Lazy Loading Reference

**⚠️ AI AGENTS: load docs on-demand — don't load everything upfront.**

A typical task needs one to three documents. Loading the whole tree costs 10–20× the tokens
and makes the relevant part harder to find, not easier.

---

## Routing Table

| When working on...         | Load                         | Path                                |
| -------------------------- | ---------------------------- | ----------------------------------- |
| **Architecture / design**  | ARCHITECTURE.md              | `docs/ARCHITECTURE.md`              |
| **Setup / config**         | DEVELOPMENT.md               | `docs/DEVELOPMENT.md`               |
| **CI/CD pipeline**         | DEVELOPMENT.md               | `docs/DEVELOPMENT.md`               |
| **Testing**                | DEVELOPMENT.md               | `docs/DEVELOPMENT.md`               |
| **CLI commands**           | CLI.md                       | `docs/CLI.md`                       |
| **Shelved / parked work**  | TODO/README.md               | `docs/TODO/README.md`               |
| **Was this built before?** | todo_index.json              | `docs/todo_index.json`              |
| **Reports of any kind**    | reports/README.md            | `docs/reports/README.md`            |
| **Ideas List** | ideas.md | `docs/ideas.md` |
| **Open — decided to build, not yet decided how** | open.md | `docs/open.md` |

<!-- SCAFFOLD: extend as docs are added. `dev check docs` fails on an unregistered doc. -->

---

## Common Scenarios

### Bug fixing
1. Read the error and stack trace.
2. Load the doc that owns that component.
3. Load ARCHITECTURE.md only if the component boundary is unclear.

### New feature
1. Load ARCHITECTURE.md for the overall design.
2. Load the component docs you will actually touch.
3. Check `docs/todo_index.json` — a plan may already exist.

### Performance issue
1. Load the performance/scaling doc first.
2. Load ARCHITECTURE.md if the bottleneck's owner is unclear.

---

## Agents, Skills & Shared Assets

[`AGENTS.md`](../AGENTS.md) at the repo root is the file every agent reads
first — the Critical Rules and the documentation routing table.
`CLAUDE.md` is a pointer to it, never a second copy.

- **Rules** (`docs/rules/`) — the conventions, one file per domain. Plain
  markdown, read because `AGENTS.md` names them. Any agent can be pointed here.

Everything under `.claude/` is Claude Code tooling and nothing else depends on
it — scaffold with `--agent none` to omit it, and the tree keeps every rule:

- **Subagents** (`.claude/agents/`) — focused workers, invoked as `@agent-<name>`.
- **Skills** (`.claude/skills/`) — multi-agent orchestration, invoked as `/<name>`.
- **Settings & hooks** (`.claude/settings.json`, `.claude/hooks/`) — a permission
  allowlist and a session-start toolchain install.

---

## Related

- Full doc list: `docs/README.md`
- Completed work: `docs/implementations/README.md`, `docs/implementation_index.json`
- Unfinished work: `docs/TODO/README.md`, `docs/todo_index.json`
