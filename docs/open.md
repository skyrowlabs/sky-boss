# Open — decided to build, not yet decided how

A running list of questions the sky.boss direction has raised and not answered. It exists because
the design pass of 2026-08-26 produced more decisions than the mockup could hold, and losing them
in a chat log is how the same argument gets had twice.

**Three lists, one test each. Keep them apart:**

| File | The question it holds |
|---|---|
| `docs/ideas.md` | *Should we build this at all?* Deleted when spec'd or shelved. |
| `docs/design/fundamentals.md` | *What is this, at the level of primitives?* Decisions accrete, dated, reversals left visible. |
| **this file** | *We are building it — how?* Items move out by being answered somewhere else. |

An item leaves this file when a feature doc, a fundamentals decision, or a deliberate rejection
takes ownership of it. **Record where it went** rather than deleting the line — the pointer is the
useful half, same rule as a feature doc's Notes.

---

## Surface

**1. The failure screen.** Every state drawn so far is nominal or gracefully degraded. There is no
rendering for a job that died mid-flight, a working-tree claim that was actually violated, or a
timer that fired outside sky.boss and left the plan wrong. [[fundamentals]] already ruled that a
dead stream goes dead visibly; nothing draws it. *Blocked on evidence — this is answered by
looking at real failures, not by drawing one.*

**2. Where the queue strip lives.** The console's per-run strip (`1082 1084 1086 …`, with dashed
slots for the deferred) was the only widget anywhere showing one run's shape at a glance. It died
with the console. It probably belongs in the tower; nothing has claimed it. See [[workbench]] Notes.

**3. The floating canvas: keep the metaphor or let it go.** [[canvas]] was built around
overlapping draggable windows and calls that the central metaphor. The mockup demoted it to one of
three layouts, and removing the console removed it entirely — the tower's `merged / split` does
the same job with structure. **This is a reversal of a stated primitive and needs an argument, not
an omission.** The case for keeping it is heterogeneous observes: a table beside a follow beside a
file cursor, which the structured views cannot express.

**4. The secondary label tier's contrast.** *Closed 2026-08-27 → [[fundamentals]] § the label
tier: a border token is not a text token.* Ruled not a contrast question at all: `TEXT_3` is
defined as *"structure, not reading text"* and is what `BORDER` is, so the mockup used a border
token as a text token. Reading text takes `TEXT_2`; the exemption is not widened. The measurement
in this item was also wrong — 1.81:1, not 2.5:1.

**5. History.** The mockup carries a `history` affordance with nothing behind it. Once a saved
command has run more than once, *how did this go the last seven nights* is the obvious question,
and the ring buffer plus the file of record already exist. Nobody owns it. *Blocked on evidence —
needs jobs that have run twice.*

## Primitives the plan and the tower need, none of which exist

These four are why [[workbench]] is buildable now and the other two screens are not. Each is
probably its own feature doc, and they are ordered by how much the others depend on them.

**6. Job identity that outlives a window.** `--label` in the mockup. Today a run is anonymous and
dies with its window. A plan, a claim, a budget and a governor all need to name the same thing
across restarts.

**7. The claim.** Several agentic jobs contending for one working tree is a real fact with no
vocabulary in sb. The mockup renders it as a glyph and a contested band; what it *means* — advisory
label, or something that actually blocks a departure — is undecided, and those are very different
features.

**8. The budget.** A wall-clock ceiling on a run. The mockup puts `--budget` on `follow`, which is
a contradiction — follow observes, and a budget that kills the child makes it act. The mockup's own
header line resolves it (sky.boss follows a foreign supervisor that owns the budget); confirm that
is the intent, or move the budget to `run`.

**9. The clock source.** sky.boss clock / crontab / systemd timer, chosen per job. Two open halves:
whether to cross the line at all (below), and **read-back drift** — every cron/systemd manager rots
where the model and the machine disagree. The mockup's `timers read 20:44` footer is a hint that
wants to become load-bearing: a per-row read-back age and a visible *drifted* state for a unit
disabled outside sky.boss.

## Boundaries

**10. The scheduler/daemon line.** [[fundamentals]] § Cadence: *nothing survives the last window —
that is what makes this a scheduler and not a daemon, and crossing that line is only ever done on
purpose.* The clock-source selector crosses it deliberately and, as drawn, honestly: per job,
explicit, with the consequence written under each option. It still needs a dated fundamentals
decision, not just a radio button in a mockup.

**11. jam.sense keeps its own scheduler.** `CLAUDE.local.md` says sb never manages, generates or
edits its cron entries — and the mockup's original cast *was* that scheduler. The cast has since
been mixed on purpose ([[workbench]] Notes), but the underlying question is untouched: does
sky.boss **observe** those entries, or does the boundary move? Defensible either way; currently
unstated, which is the one thing it should not be.

**12. `--save` invoked from a surface.** *Closed 2026-08-27 → [[workbench]] Notes, ratified as
proposed.* Stronger than the item assumed: the bench adds no execution path ([[canvas]] already
runs subprocesses) and `--save` already composes with a cadence, so the bench composes a one-liner
the CLI supports rather than teaching it anything. Held by a test — no route writes `tools.toml`.
Two consequences of `--save` writing *before* it runs became round-3 items there.

## The Governor

**13. What it costs, and what it does when it cannot run.** The governor is LLM narration over a
log — the strongest idea in the mockup and the only panel doing something a terminal cannot. Open:
who calls it, on what cadence, against what budget, and what the panel shows when the model is
unavailable. It must degrade to the raw events rather than going blank. Also unsettled: it is the
only *mechanical* metaphor in an otherwise clean aviation set, though it does describe the
budget-limiting function accurately.

---

## Going public, and stopping being one person

Opened 2026-08-27, when the repo's audience changed from *the operator* to *whoever clones it*.
Several decisions in `CLAUDE.md` were made against a one-contributor repo and were correct for it;
they are not automatically correct for a public one, and this is where that gets argued rather
than drifted into. What was *done* that day — MIT, CI, the slug-resolution test, the history
scrub — is recorded in `CLAUDE.md` and `CLAUDE.local.md` § Publication status; only the two
questions below are still open.

**14. Lint for the JavaScript.** *Closed 2026-08-27 → `eslint.config.js` and `package.json` at
the repo root, gated by the `lint` job in `.github/workflows/ci.yml`.* Adopted because [[workbench]]
is the "something needs them" the item was waiting for — `app.js` is ~1000 lines and the bench adds
a screen, and a ratchet retrofitted afterwards baselines the bugs you just wrote. Clean on arrival:
9 files, 0 errors, 0 warnings, so `--max-warnings=0` starts at zero and may only go down.

Three constraints held. **No Prettier**, and none on `cli/canvas/static/` ever — the `htm` comment
hazard is a formatter's bug with authority behind it. **Config lives at the root, never in
`cli/canvas/static/`**, which is served wholesale and has a declared inventory a stray config would
break. **Vendored code is exempt**, the same rule the hex scan uses. The Electron files are not
split by process: `preload.js` bridges both by design, so a strict split would flag correct code.

**15. Which of skeletor's governance the second contributor actually needs.** Deliberately not
answered on the day, because the honest answer depends on whether a second contributor arrives.
The ones whose *justification changes* the moment one does — each was declined on 2026-08-27 on
single-contributor grounds, and that ground is going away:

| From skeletor | What it is for | Why it was declined |
|---|---|---|
| PR + issue templates, `CODEOWNERS` | Shaping an outside contribution into something actionable | Nobody outside to shape |
| Draft-PR discipline, the CI gate job | Keeping Actions minutes off abandoned iterations | One person, one branch, a 5s suite |
| `dependabot.yml` | Bumps that run the suite before auto-merge | No PR flow to run in |
| Conventional-commit hook | The log already reads this way — a hook makes it hold for someone new | Habit sufficed |
| Coverage / skip ratchets | Catching a suite that quietly stopped testing | Nobody to catch |

**Not on that list, and still declined for reasons a contributor count does not touch:** the docs
lifecycle machinery — generated indexes, `TODO/` ↔ `implementations/`, frontmatter, merge drivers.
`CLAUDE.md`: *"No index machinery yet. There was a generated one; it went with the docs."* The
split this repo uses instead — [[open]], `ideas.md`, [[fundamentals]], one doc per feature — is a
different design, not a smaller one. Also still out: `release-please` and a `VERSION` file, because
the version comes from `git describe` and `cli/banner.py` prints it; a tracked `VERSION` is a
second source of truth that can disagree with the tag, and the mark would be where it showed.
