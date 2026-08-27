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

**4. The secondary label tier's contrast.** 10.5px `#344050` on `#0b1016` measures roughly 2.5:1.
The CLI holds a measured 3.5:1 floor and the canvas is exempt because it paints its own
background — but that exemption was written for **the mark**, not for an entire tier of labels
(`QUEUE · 8`, `LAYOUT`, on-deck times). Either widen the exemption on purpose or lift the tier.

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
vocabulary in tb. The mockup renders it as a glyph and a contested band; what it *means* — advisory
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

**11. jam.sense keeps its own scheduler.** `CLAUDE.local.md` says tb never manages, generates or
edits its cron entries — and the mockup's original cast *was* that scheduler. The cast has since
been mixed on purpose ([[workbench]] Notes), but the underlying question is untouched: does
sky.boss **observe** those entries, or does the boundary move? Defensible either way; currently
unstated, which is the one thing it should not be.

**12. `--save` invoked from a surface.** [[workbench]] round 3 proposes the bench composes the
argv and runs `--save` as a subprocess, so `--save` stays the only writer and the surface gains no
route that touches `tools.toml`. That reading looks sound and should be ratified explicitly,
because "no surface writes" is the kind of rule that erodes by reasonable-looking steps.

## The Governor

**13. What it costs, and what it does when it cannot run.** The governor is LLM narration over a
log — the strongest idea in the mockup and the only panel doing something a terminal cannot. Open:
who calls it, on what cadence, against what budget, and what the panel shows when the model is
unavailable. It must degrade to the raw events rather than going blank. Also unsettled: it is the
only *mechanical* metaphor in an otherwise clean aviation set, though it does describe the
budget-limiting function accurately.

---

## The rename, finished and unfinished

Current-tense prose was renamed **toolbox → sky.boss** on 2026-08-26 (`CLAUDE.md`, `README.md`,
`docs/design/README.md`, the feature skill). Three categories were left alone on purpose. Two of
them are settled and need no decision; one is a real open question.

**Settled, no action:**

- **The common noun.** "The toolbox" — the box of saved commands `tb tools` lists — was never the
  project's name and stays. [[tools]] ruled on exactly this at the previous rename and recorded
  why: *nothing in the prose was scrubbed, because that is what it is.*
- **Dated records.** Completed feature docs and measurement transcripts keep the word. Scrubbing a
  transcript falsifies a measurement, and the same rule already leaves `wrap`/`every` standing in
  docs that predate the 2026-08-21 command renames.

**14. The identifier cluster — one decision, not four.** These are coordinated and should move
together or not at all. **`tb` itself is not in scope** and is not proposed for change.

- `~/.toolbox` — the `$TB_HOME` default. Operator data. Renaming needs a migration path, or every
  existing `tools.toml`, `formats.toml` and `projects.toml` silently stops being found.
- The **window class** `toolbox` (`cli/canvas/shell.py`, `--class=` on the browser path) and the
  app names beside it. `CLAUDE.local.md` records a window-manager rule matched on this string, and
  `CLAUDE.md` is explicit that nothing here writes that rule — so renaming it means the frameless
  window regains a title bar until the operator updates the rule by hand. A rename and a desktop
  edit, in that order, or neither.
- The **MCP server name** — `.mcp.json`'s key, `serverInfo.name` in `cli/mcp.py`, and the assertion
  in `tests/test_mcp.py`. Renaming changes the tool names agents see (`mcp__toolbox__*`), so it is
  a change to a published interface, not to a string.
- **The mark.** `docs/design/cli-header.png` is a drawing of a toolbox with `TOOLBOX` lettered
  across it, printed beside the word by `cli/banner.py` and asserted by `tests/test_banner.py`.
  **Renaming the word without redrawing the mark leaves the CLI greeting you with a picture of the
  old name.** This is a [[header]] round and a design task, not a substitution — and [[header]]
  records that the mark is the one thing outside the theme's contrast floor, so a redraw inherits
  that argument too.
- `shell/package.json`'s `toolbox-shell`, and the `.toolbox` CSS classes in `tb.css` / `app.js`.
  Internal; churn with no reader unless the cluster moves anyway.
