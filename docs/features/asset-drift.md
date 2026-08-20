---
slug: asset-drift
title: Baseline refresh and inventory revalidation — tb assets update
status: active
created: 2026-08-18
updated: 2026-08-18
agent_value: 2
key_files:
  - cli/assets.py
  - tests/test_assets_update.py
---

# Baseline refresh and inventory revalidation — `tb assets update`

## Why

[[machine-baseline]] answers "what is this machine right now." It does not answer "has anything
changed since we recorded it." A baseline that is only ever generated is a snapshot; a baseline
that is re-derived and compared is a monitor.

The facts that drift are exactly the ones that cause silent breakage: a kernel or driver bump, a
changed login shell, a new default browser, a timezone that moved, a disk that was swapped. Each
is invisible until something depending on it fails.

**This updates tb's record of the machine, not the machine.** It installs nothing and upgrades
nothing.

## Shape

`tb assets update` — re-derive the baseline, compare it against what is recorded in
`inventory/<host>.yaml`, and report the drift.

- `--section <name>` targets one section group; omitted, all sections. This is the "targets
  groups" half.
- `--host <name>` / `--all` — same targeting as `describe`. Broad by default.
- `--apply` refreshes the **derived** fields in inventory with current reality.

Exit behavior follows the contract: no drift is `0`, drift found is `partial` (`3`), a host that
could not be reached is a warning that also degrades. That makes it usable as a scheduled job
whose non-zero exit means "something about a machine changed."

**Derived and declared fields are strictly separated.** `--apply` may only ever rewrite fields
`describe` produces. Declared fields — role, purchase date, location, notes, anything a human
wrote — are never touched, never reordered, never reformatted. The git diff of inventory is the
maintenance log, and a command that churns hand-written context destroys that log.

**Drift is reported, not silently absorbed.** Even with `--apply`, every change is printed. The
point is to notice, not to converge quietly.

**Does not do:**

- **No package, OS, or application updates.** Nothing is installed, upgraded, or restarted. Only
  tb's own record changes.
- No writing to a host it describes. Remote hosts are read-only; only the local inventory file
  is written.
- No creating inventory files — that is `describe --seed`. A host with no inventory file is
  reported as unrecorded, not silently seeded.
- No history or trend tracking. This compares now against recorded, nothing more.

## Phases

### Phase 1 — Compare

- [x] Load `inventory/<host>.yaml` and split derived vs declared fields
- [x] Re-run the requested sections via the `describe` registry
- [x] Structural diff, reported as a table: field, recorded, current
- [x] No drift exits 0; drift degrades to partial
- [x] Unrecorded host reports clearly rather than erroring

### Phase 2 — Apply

- [x] `--apply` rewrites derived fields only, leaving declared fields byte-identical
- [x] Test asserting a hand-written comment and declared field survive `--apply` untouched
- [x] Print every change applied

### Phase 3 — Fleet-wide

- [ ] `--all` across reachable hosts, one inventory file each
- [ ] An unreachable host degrades without blocking the rest

## Notes

[[machine-baseline]] is complete, so the section registry and `inventory_record` split already
exist and Phases 1–2 here are unblocked for the local machine.

Phase 3 (fleet-wide) depends on [[asset-remote]] for the SSH runner and host targeting, which is
itself blocked on unattended tailnet SSH — see that doc's prerequisite section.

**Phase 1 (2026-08-18).** Records are compared **flattened**, not structurally. Nested dicts drop
one level so a Python bump reports `runtimes.python: 3.13.0 -> 3.14.7` rather than dumping every
interpreter as one changed blob.

Lists are compared as a **sorted** summary string. Comparing positionally would make a kernel
reordering `disks` look like a hardware change — noise that trains you to ignore the output.

The comparison walks the **union** of both key sets, so a runtime that disappeared is drift just
as much as one that changed.

`--section` scopes through `FIELD_SECTION`, which maps each inventory field to the section it
derives from. Without it, `--section os` would report every field it did not collect as drift
against nothing. `identity` is always collected regardless, since the hostname is how the record
is found.

An unrecorded host is `ok: false` with a hint to seed one — clear reporting, not a traceback.

Verified live by perturbing kernel and `runtimes.python` in the record: both detected, exit 3,
warnings on stderr, record restored from git afterwards.

**Phase 2 (2026-08-18).** `--apply` rewrites the `derived:` block by **textual surgery**, not a
YAML round-trip. Loading and re-dumping the file would discard every comment — the `declared:`
placeholders and any note written beside a field, which is the maintenance log this repo exists
to keep. The block is anchored on top-level keys at column zero, so everything before `derived:`
and from the next top-level key onward survives byte for byte. There is a test that fills in a
declared field with an inline note and asserts it is untouched.

A scoped `--apply` **merges** rather than writing wholesale: `--section os` re-derives only the
os fields, so writing `current` directly would blank every field it never looked at.

Comments *inside* the derived block are not preserved. That block is machine-written and the file
header says so.
