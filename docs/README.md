# sky.boss Documentation

One CLI for watching what other tools do, here and across these repos

**⚠️ AI AGENTS**: use lazy loading. See [`.github/DOCS_INDEX.md`](../.github/DOCS_INDEX.md)
for the routing table — load only the documents a task needs.

---

## Structure

**Root `docs/`** holds current, critical reference. Everything else is a lifecycle stage:

| Folder             | Holds                                                     |
| ------------------ | --------------------------------------------------------- |
| `TODO/`            | The **holding tank** — every plan that is not finished    |
| `implementations/` | The **archive** — completed plans, moved here when done   |
| `reports/regular/` | In-flight periodic reports, anchored to the current window |
| `reports/releases/` | Frozen per-release editions — never edited                |
| `reports/occasional/` | One-time deep dives and sweeps                          |
| `research/`        | Feasibility work and decision memos                       |

---

## Core Reference

| Document                             | Purpose                                       |
| ------------------------------------ | --------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)   | System design, components, critical patterns  |
| [DEVELOPMENT.md](DEVELOPMENT.md)     | Setup, configuration, CI/CD, testing          |
| [CLI.md](CLI.md)                     | CLI architecture and command reference        |

<!-- SCAFFOLD: add this project's own reference docs here and in DOCS_INDEX.md -->

---

## Holding Tank — Unfinished Work

- **[TODO/README.md](TODO/README.md)** — status-grouped index of every unfinished plan
- **[todo_index.json](todo_index.json)** — machine-readable (status, gate, priority, tags)

Load `todo_index.json` to answer *"is this already built but parked?"* **before** rebuilding
a feature.

## Conventions

- **[rules/](rules/)** — one file per domain: commits, docs, testing, output,
  and the language rules. `AGENTS.md` points here; they are read, never
  auto-loaded, so they work with any agent.

## Archive — Completed Work

- **[implementations/README.md](implementations/README.md)** — index by category
- **[implementation_index.json](implementation_index.json)** — machine-readable

Both READMEs and both JSON files are generated. Never hand-edit — see
[`docs/rules/docs.md`](rules/docs.md).
