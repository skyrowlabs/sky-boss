---
slug: bookmarks
title: Bookmark repository manager
status: draft
created: 2026-08-19
updated: 2026-08-19
agent_value: 2
key_files: []
---

# Bookmark repository manager

> **Idea capture, not a spec.** Recorded 2026-08-19 so the machine survey below does not have to
> be redone. No phases yet — write them when this gets picked up.

## Why

Bookmarks scatter across every browser on a machine and there is no shared store. The wanted
outcome: the same bookmarks in Firefox and Chrome on workstation, with Brave and Chromium
deliberately excluded — so participation must be configuration, not a hardcoded list.

## What workstation actually looks like (surveyed 2026-08-19)

| Browser | Binary | State |
|---|---|---|
| Firefox | `/usr/bin/firefox` (**Flatpak**) | **No profile.** `~/.var/app/org.mozilla.firefox/.mozilla/` holds only `native-messaging-hosts` — never run |
| Chrome | `/usr/bin/google-chrome-stable` | 1 bookmark (a Grafana dashboard). **Not signed in** — no Google cloud sync |
| Chromium | `/usr/bin/chromium` | 1 bookmark (jam.sense). A fourth browser, not in the original ask |
| Brave | `/usr/bin/brave` | **No profile.** No `Default/`, no `Bookmarks` file |

Two bookmarks exist on the whole machine. Nothing is at risk, which makes this a good thing to
build *before* bookmarks accumulate in four places — but Firefox needs one launch before it can
be a target at all.

Firefox being a Flatpak is not an obstacle: `tb` runs outside the sandbox and the profile is a
normal host directory at `~/.var/app/org.mozilla.firefox/.mozilla/firefox/<profile>/`.

## Findings

### Linking the stores is not possible

- **Firefox ↔ Chrome: categorically impossible.** Firefox uses `places.sqlite` (SQLite;
  `moz_bookmarks` + `moz_places`, with a WAL). Chrome uses a JSON file. No filesystem mechanism
  bridges those.
- **Chrome ↔ Brave ↔ Chromium: looks possible, silently fails.** They share an identical JSON
  format, so a symlink or hardlink between profiles seems obvious. But Chromium writes bookmarks
  by creating `Bookmarks.tmp` and `rename()`ing it over the target. That atomic replace
  **destroys a symlink** and **breaks a hardlink**; a bind mount stays pinned to the stale inode.
  The link holds until the first bookmark change, then stops linking with no error. Silent
  divergence is worse than no sync.

### The two hard parts of true sync

1. **Deletion is undecidable from current state.** A bookmark present in Chrome and absent in
   Firefox is either an addition on one side or a deletion on the other, and the two states cannot
   distinguish them. Every real bidirectional syncer solves this with a shadow copy of the
   last-synced state and a three-way merge. Everything else is format plumbing; this is the
   difficulty.
2. **You cannot write to a running browser.** Chrome keeps bookmarks in memory and rewrites the
   file on every change, so external writes are clobbered at the next write. Firefox holds
   `places.sqlite` open with a WAL and writing underneath risks corruption. Any external tool has
   a hard precondition: **the target browser must be closed.**

### Options considered

**A — floccus (existing, extension-based).** Extensions for Firefox/Chrome/Brave syncing through
WebDAV, Nextcloud, or Google Drive. Architecturally the strongest, for one reason: **the browsers
write their own stores**, so both hard parts above disappear. Costs: an extension per browser, a
sync backend, and it is not `tb`.

**B — `tb` as a bidirectional reconciler.** Read both stores, three-way merge against a shadow,
write back when browsers are closed. Full control and a ledger entry. Cost: you own the merge
bugs, and merge bugs eat bookmarks.

**C — a declared system of record (recommended).** One versioned file in the repo is the truth;
`tb` renders it into each enabled browser. Deletion becomes trivial — remove the line, push, gone
everywhere. No shadow, no merge, no undecidability.

## Sketch, if built (option C)

C is recommended because it is the pattern the repo already runs on: `inventory/workstation.yaml` is
a versioned system of record whose git diff is the maintenance log, split `declared:` / `derived:`.
Bookmarks are the same shape. It also reaches other machines free — the file is in git, so laptop
pulls the same bookmarks.

```
tb info bookmarks          # what is declared, and where each browser has drifted
tb check bookmarks         # verdict: which enabled browsers are stale
tb run bookmarks-capture   # promote NEW bookmarks from the capture browser into the file
tb run bookmarks-push      # render the file into every enabled browser
```

The ergonomic objection — you star things in a browser, not in a text file — is answered by
**capture**, which only ever *adds*. Anything in the capture browser and not in the file is new,
which is decidable with no shadow state. Deletion happens only by editing the file. That single
asymmetry buys the entire distributed-systems problem for free.

Participating browsers and the designated capture browser live in `$TB_HOME/bookmarks.toml`,
per the machine-local config convention.

**Safety rail for v1: `tb` owns exactly one folder.** A `tackle-box` folder in each browser's
bookmarks bar; everything outside it is the human's and is never read for drift or touched on
push. A push bug then costs nothing. Widen to the whole tree only once it is trusted.

Fits the command taxonomy with no new top-level group — a decent live test of it.

**Does not do:** no cloud backend, no browser extension, no history/tabs/passwords — bookmarks
only.

## Notes

**`check` is schedulable, `push` is not.** Push has a precondition a timer cannot guarantee (the
browser being closed), so `tb check bookmarks` can join the daily jobs while push stays manual.

**Unverified, to confirm before writing Chrome's store:** the `checksum` field in Chrome's
`Bookmarks` JSON is an MD5 over a serialization of the tree. Chrome validates it and treats a
mismatch as corruption. Whether it silently regenerates or discards ordering/metadata was not
tested — test it on a throwaway profile before any write path ships.
