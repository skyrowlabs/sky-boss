---
slug: locations
title: Key locations — a registry and a two-way channel
status: draft
created: 2026-08-18
updated: 2026-08-18
agent_value: 3
key_files: []
---

# Key locations — a registry and a two-way channel

## Why

The obvious problem is that things are not where they belong. Measured in `~/Downloads` on
2026-08-18 — 30 GB across 192 files, no structure, while `~/Pictures` is empty and `~/Documents`,
`~/Videos` and `~/Music` do not exist:

- `Photos-3-001` and `Photos-3-001.zip` both present — an archive extracted beside itself.
  **4.3 GB of exact duplication.**
- Four ISOs and a Manjaro `.img.xz`: **~13 GB of re-downloadable installers.**
- An 8 GB `wtk-led-climate_wind_speed_uncertainty_40m.zip` — wind-resource data that belongs with
  breeze.brain.
- 93 JPGs and 39 MP4s where no photo application will look for them.

The *deeper* problem is the other direction. There is no addressable map of where anything lives,
so retrieval is guesswork — `find ~ -name '*wind*'` and hope. Filing things away is only half a
system; **the half that is always missing is getting them back.**

None of this is a storage problem. The disk is 3.6 TB and 65% free. It is an addressing problem,
and it is not solved by more infrastructure.

## Shape

Three layers, and the separation between them is the design.

### 1. The registry — declared, and the ground truth

`locations.yaml` in the repo: named locations, each with a path, a kind, and a note on what
belongs there. Versioned, so the git diff records why the map is what it is — the same treatment
as `inventory/`.

```yaml
photos:      { path: ~/Pictures,                        kind: media,   holds: "photos, by year/month" }
video:       { path: ~/Videos,                          kind: media,   holds: "video, by year" }
datasets:    { path: ~/library/data,                    kind: data,    holds: "datasets not owned by a project" }
installers:  { path: ~/library/archive/iso,             kind: archive, holds: "OS images; re-downloadable" }
breeze-data: { path: ~/src/breeze.brain/data,   kind: project, holds: "wind/solar resource data" }
inbox:       { path: ~/Downloads,                       kind: inbox,   holds: "nothing — transit only" }
```

A location is a **name you can address**, not a path you have to remember. Names are the interface;
paths are an implementation detail that can change without anything else changing.

### 2. The base — prescriptive, and complete without any agent

Every operation is exact, predictable, and expressible as a command you could type yourself.
**This layer must be fully usable with no agent involved.** Two directions:

- **Retrieve** — `tb find <pattern>` searches the registered locations and reports where matches
  are, with size and age. `tb loc show <name>` says what a location holds and what is in it.
- **Deposit** — `tb loc put <file> <location>` places a file in a named location under that
  location's convention (dated subdirectory for media, flat for archives).

Nothing here guesses. A pattern either matches or it does not; a location either exists in the
registry or the command fails.

### 3. Agentic governance — a layer on top, and strictly optional

The agent turns intent into base operations: "where's that wind data" resolves to a `find`;
"put this somewhere sensible" resolves to a `put` against a named location, with a stated reason.
It also governs over time — noticing an inbox filling up, spotting a kind of file with no location
to hold it, proposing a registry entry.

**Hard rule: the agent may only invoke base operations.** Anything it wants to do must be
expressible as a command the base already supports. It never moves a file by another route, and
never invents a destination outside the registry. If the agent needs something the base cannot
express, the base is what gets extended — and then the deterministic path gets it too.

This is the same rule the output contract uses: the agent proposes into the format the
deterministic path executes.

### Safety, for the write direction

- **Never delete. Ever.** Duplicates and reclaimable installers are *reported* with the bytes they
  represent. Removing them is a human decision. No quarantine directory either — a trash that tb
  manages is deletion with extra steps.
- **Never overwrite.** An occupied destination is a reported conflict, not something resolved
  automatically.
- **Dry-run is the default.** `--apply` is required to move anything.
- **Every applied move is journaled** — source, destination, sha256, batch id — to
  `~/.local/state/tb/locations/`, outside the repo so `git clean` cannot destroy the record that
  makes moves reversible.
- **Verify after moving**, and fail loudly on a hash mismatch.
- **Hash lazily.** Size is a free discriminator; hash only within colliding size groups rather
  than hashing 30 GB.

**Does not do:**

- **No content search.** This finds files by name, kind, size and age — not by what is inside them.
  Knowing *where a thing lives* is the goal; full-text indexing is a different product.
- **No deletion, no trash, no quarantine.**
- **No renaming.** Moving is already the risky operation.
- **No storage infrastructure** — no mounts, filesystems, NAS, RAID, or capacity management.
- **No sync.** Dropbox and Google Drive are a backup destination, a separate concern.
- **No daemon or watcher.** Nothing runs continuously; this is invoked, or scheduled as a job.
- **No remote locations in v1.** The registry schema should leave room for a `host:` field so
  [[asset-remote]] can extend it later, but every location here is local.

## Phases

### Phase 1 — Registry and resolution

- [ ] `locations.yaml` schema: name, path, kind, holds; `~` expansion; validation on load
- [ ] `tb loc list` — every location with kind, path, whether it exists, item count
- [ ] `tb loc show <name>` — what it holds and what is in it
- [ ] Unknown name fails with the valid names listed
- [ ] A declared path that does not exist is reported, not created
- [ ] Schema reserves `host:` for later remote locations without implementing it

### Phase 2 — Retrieve

- [ ] `tb find <pattern>` across registered locations: name glob, with size and mtime
- [ ] `--kind` and `--location` narrow the search
- [ ] Results ordered most-recent-first, since recency is usually why you are looking
- [ ] Searching an inbox is included by default — that is where lost things are
- [ ] No index: walk on demand. Revisit only if a real corpus makes it slow

### Phase 3 — Deposit

- [ ] `tb loc put <file> <location>` — dry-run by default, `--apply` to act
- [ ] Per-kind placement convention (media dated, archive flat)
- [ ] Journal with sha256 and batch id to `~/.local/state/tb/locations/`
- [ ] Refuse on conflict; verify hash after move; a conflict skips that file, not the batch
- [ ] `tb loc undo <batch>` reverses a batch, refusing if a file changed since

### Phase 4 — Inbox triage

- [ ] `tb loc triage` — classify inbox contents against the registry deterministically
- [ ] Exact duplicates by size-then-hash, with reclaimable bytes
- [ ] The archive-beside-its-extraction case (`X.zip` next to `X/`)
- [ ] Re-downloadable installers flagged separately from true duplicates
- [ ] Unclassified files reported as unclassified, never guessed at

### Phase 5 — Agentic governance

- [ ] Resolve fuzzy intent to a base operation, with the resolved command shown before it runs
- [ ] Propose destinations for triage residue, each with a stated reason and a confidence
- [ ] Propose registry entries when a kind of file has nowhere to go
- [ ] Low confidence marked and never auto-applied
- [ ] Test asserting the agent path produces only base operations — no direct filesystem writes

## Notes

The registry is the reason this is more than a tidier. Once locations have **names**, the same map
serves retrieval, filing, backup targeting, and eventually remote hosts — and each of those stops
hard-coding paths.

Destination split, decided 2026-08-18: media to XDG directories because applications already look
there; everything else under a `~/library` root that can move to a NAS later as one tree; project
data to the project, because a dataset separated from the work that uses it is how it gets lost.

EXIF needs a decision in Phase 3 — a Python dependency or an external tool. mtime is the fallback,
though for an extracted takeout mtime is the extraction date, not the capture date.

Supersedes the earlier `tidy` spec, which had only the filing direction. Retrieval turned out to be
the more valuable half and the registry is what makes both work.
