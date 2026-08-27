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
`docs/design/README.md`, the feature skill). Three categories were left alone. **On 2026-08-27 the
operator moved all three**, and the record below is kept rather than deleted because two of them
were written down here as *settled, no action* and it is worth being able to see that they were
reversed and on whose word.

**What was settled, and is no longer:**

- **The common noun.** "The toolbox" — the box of saved commands `sb tools` lists — was never the
  project's name and was to stay. [[tools]] had ruled on exactly this at the previous rename and
  recorded why: *nothing in the prose was scrubbed, because that is what it is.* **Reversed.** The
  `tb` → `sb` rename took the word with it, so the container lost its nickname instead of gaining
  a new one: it is **the tools**, which is what the command was already called. The argument that
  fell is that the collection needs a noun of its own at all.
- **Dated records.** Completed feature docs and measurement transcripts were to keep the word.
  **Reversed** — `docs/features/done/` was scrubbed too. One consequence to know about:
  [[subprocess-env]]'s measurement transcript now reads `jam from sky-boss`, which is the directory
  it would be run from *today* but not the one it was captured from. The measurement is unchanged
  and its conclusion does not depend on the directory's name.

**14. The identifier cluster — one decision, not four.** *Closed 2026-08-27: moved as one, plus
`tb` → `sb`, which this item had explicitly held out of scope.*

- `$SB_HOME` now defaults to `~/.sky-boss`. The migration path this item asked for is
  `_default_home()` in `cli/helpers.py`: the old `~/.toolbox` still wins while it is the only one
  that exists, and the bridge stops applying the moment the new path does. No merge — two homes at
  once would make *which* `tools.toml` you are editing a coin toss.
- The **window class** is `sb`. As warned, this is a rename *and* a desktop edit: the frameless
  canvas regains a title bar until the window-manager rule matching the old string is updated by
  hand, and nothing here writes that rule.
- The **MCP server name** is `sky-boss`, in `.mcp.json`, `serverInfo.name` and the test. Agents now
  see `mcp__sky-boss__*`; anything wired to the old tool names is broken until it is repointed.
  This was the published-interface break the item flagged, taken knowingly.
- `shell/package.json` is `sky-boss-shell`, and the sidebar's CSS is `.tools` / `.tools-head` /
  `.tools-list` / `.tools-empty` / `.tools-foot`, which now pairs with the `.tool` row classes that
  were always there.

**15. The mark.** *Opened and closed 2026-08-27.* Split out of item 14 as the one part of the
cluster a substitution could not move: `docs/design/cli-header.png` was a drawing of a toolbox with
`TOOLBOX` lettered across it, printed beside the word by `cli/banner.py` — which had started
printing **sky.boss**. So `sb --help` greeted you with the new name next to a picture of the old
one.

Redrawn the same day as a **control tower**, which is the metaphor the artboards already speak.
[[header]] round 2 has the design; the two things worth knowing here are that the glyph fits the
same 63-column art so nothing about the panel moved, and that the source direction inverted —
`ART` in `banner.py` is now the picture and `docs/design/render-mark.py` renders both PNGs from it.
Round 1 had measured the tuple *off* the PNG, which is precisely the arrangement that let a rename
change one and not the other.

---

## Going public, and stopping being one person

Opened 2026-08-27, when the repo's audience changed from *the operator* to *whoever clones it*.
Several decisions in `CLAUDE.md` were made against a one-contributor repo and were correct for it;
they are not automatically correct for a public one, and this is where that gets argued rather
than drifted into.

Three things were taken from **skeletor** (`~/src/skeletor`, the sibling scaffold generator) the
same day, and they are settled rather than open:

- **`LICENSE`.** Verbatim MIT, `SKYROW LABS LLC`, byte-identical to skeletor's body so GitHub
  resolves it as MIT rather than "Other" — skeletor learned that the hard way and the lesson is
  free. This closes the last item in `CLAUDE.local.md` § Publication status. No `NOTICE`: that file
  exists in skeletor to unencumber *scaffolded output*, and nothing here scaffolds.
- **CI** — `.github/workflows/ci.yml`, the whole suite on push and PR. Skeletor's is 202 lines of
  draft-PR cost gating solving a problem this repo does not have: the suite is 676 tests in under
  five seconds with no network, so deciding whether to run it costs more than running it.
- **A slug-resolution test** — `tests/test_docs.py`, the sky.boss-shaped version of skeletor's
  `check_source_doc_refs.py`. It found two dead references on its first run.

**16. Lint for the JavaScript.** The canvas is three hand-written `.js` files and the Electron
shell is five more, and `CLAUDE.md` concedes *"the frontend has no automated tests"*. Skeletor's
`template/node/` overlay is correctness-only ESLint — `eqeqeq`, `no-var`, `prefer-const`,
`no-unused-vars` — with Prettier owning formatting and a whole-tree warning ratchet.

Against it, and the reason this is open rather than done: `CLAUDE.md` says *"No `pyproject.toml`,
pyright, or pre-commit until something needs them"*, and the same bar applies here. A growing
Electron app is a plausible "something"; a linter that arrives before the thing it lints is not.

**Whatever is decided, do not point Prettier at `cli/canvas/static/`.** `CLAUDE.md` records that
`htm` has no notion of a comment and that whitespace in tag position silently mangles an element's
children — *one comment in a `<div>` opening tag removed an `<input>` from the DOM entirely, and
only rendering the page found it*. A formatter reflowing `html\`…\`` templates is that same hazard
with a tool's authority behind it. ESLint reads; Prettier rewrites. They are not one decision.

**17. Which of skeletor's governance the second contributor actually needs.** Deliberately not
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
