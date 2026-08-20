---
slug: machine-baseline
title: Machine baseline — tb assets describe
status: complete
created: 2026-08-18
updated: 2026-08-18
agent_value: 3
key_files:
  - cli/assets.py
  - inventory/_template.yaml
  - cli/runner.py
  - cli/output.py
---

# Machine baseline — `tb assets describe`

## Why

There is no single answer to "what is this machine." Facts are scattered across `hostnamectl`,
`/etc/os-release`, `lscpu`, `lsblk`, `nvidia-smi`, `timedatectl`, `xdg-settings`, `pacman`,
`docker` and `systemctl`, and nothing collects them — on workstation or on any other node.

The cost of not having it is already demonstrated. Six turns of work assumed bash because every
tool spawns bash, while the login shell is `/bin/fish` — which is why `tb` silently resolved to
CachyOS's `termbin` alias instead of this CLI. Likewise `node-01`'s four RTX Pro 4000s were easy
to mentally attach to workstation; workstation reports one GPU.

This is also the natural second consumer of [[output-contract]]. It fans out across a dozen
sources on several hosts, any of which can be absent, offline, or unauthenticated — exactly the
shape `partial` exists for.

## Shape

`tb assets describe` — a read-only report, grouped into sections, over one or many hosts.

- `--section <name>` narrows to one section; omitted, all sections run.
- Local machine only. Remote targeting (`--host`, `--all`) belongs to [[asset-remote]].
- `--json` emits the whole structure, which is what makes this the seed for inventory.

**A `Runner` abstraction is the core of the design, not an afterthought.** Sections are written
against a runner that executes an argv list and returns output. `LocalRunner` shells out here;
[[asset-remote]] adds the SSH transport with the same interface, so no section changes. No
section may call `subprocess` directly, or it silently becomes local-only — which is precisely
the property that lets the transport be swapped later.

**Every source and every host degrades independently.** A missing tool, an offline node, or a
host that cannot authenticate records a warning and marks the result partial. One dead source
must never cost you the other eleven, and one unreachable host must never cost you the fleet.

**No sudo, ever.** `/sys/class/dmi/id/*` is world-readable, so `dmidecode` is unnecessary. A
baseline that prompts for a password could never run unattended as a job.

**Never interactive over SSH.** `BatchMode=yes`, an explicit `ConnectTimeout`, and a hard
wall-clock timeout. A prompt that blocks forever is the failure mode this must not have — see
Notes for the current state of tailnet SSH auth, which is unresolved.

Sections, all unprivileged:

| Section | From |
|---|---|
| `identity` | `hostnamectl`, `/sys/class/dmi/id/*`, uptime |
| `os` | `/etc/os-release`, `uname`, `pacman -Q` count, `pacman -Qu` pending |
| `shell` | login shell from `getent passwd`, `/etc/shells`, PATH entries |
| `settings` | `timedatectl`, `localectl`, `systemctl get-default`, desktop/session type |
| `apps` | `xdg-settings get default-web-browser`, `mimeapps.list`, `EDITOR`/`VISUAL`/`PAGER` |
| `cpu` | `lscpu` |
| `memory` | `/proc/meminfo` |
| `storage` | `lsblk`, `df` |
| `gpu` | `nvidia-smi --query-gpu` |
| `network` | `ip -j addr`, `tailscale status --json` |
| `runtime` | `docker ps`, `systemctl --user list-units` |

**Does not do:**

- **Does not install or apply any update.** Pending package counts are *reported*; nothing is
  upgraded. Application/package update management is explicitly out of scope for now.
- **Never dumps the environment.** PATH is reported because it is load-bearing for `tb` itself,
  and `EDITOR`/`VISUAL`/`PAGER` because they are user settings. No other environment variable is
  read or emitted. Env is where secrets live.
- **Never writes inventory automatically.** Inventory is a hand-maintained system of record whose
  git diff is the maintenance log. The seed phase writes once and refuses to overwrite.
- No drift detection or reconciliation — that is [[asset-drift]].
- No temperature or sensor data — parked on the jobs backlog.
- **No live metrics.** No uptime, no free memory, no load. Those change by the minute and are
  machine *health*, which is a job (see `docs/jobs-backlog.md`), not a baseline.

## Phases

### Phase 1 — Registry, runner, and identity sections

- [x] `cli/assets.py` with a `assets` group, registered in `cli/__init__.py` under an alias
- [x] `Runner` protocol + `LocalRunner`; sections take a runner and never touch `subprocess`
- [x] Section registry: name → callable, so sections are independently testable
- [x] Runner loop catching per-section failure into `degrade()`
- [x] Sections: `identity`, `os`, `shell`
- [x] `--section`, validated against the registry

### Phase 3 — Settings and default applications

- [x] Sections: `settings`, `apps`
- [x] `apps` reports absent defaults as unset rather than failing

### Phase 4 — Hardware

- [x] Sections: `cpu`, `memory`, `storage`, `gpu`
- [x] `gpu` reports cleanly on a machine with no GPU rather than warning
- [x] Sizes carried as bytes in `data`, humanized only by the renderer

### Phase 5 — Inventory seed

- [x] `--seed` writes `inventory/<hostname>.yaml`: derived facts plus commented placeholders for
      non-derivable ones (role, purchased, location, notes)
- [x] Refuses to overwrite an existing file; says what to do instead
- [x] `inventory/_template.yaml` documenting the fields

### Phase 6 — Network and runtimes

- [x] Section: `network` — interfaces with global addresses, plus tailnet address and name
- [x] Skip loopback and container bridges; they belong to the workload, not the machine
- [x] Section: `runtimes` — interpreters and toolchains with versions
- [x] Absent tools omitted rather than listed as null
- [x] Drop live metrics from the baseline (uptime, available memory)
- [x] Inventory records the occasionally-changing software layer: kernel, login shell,
      default browser, runtime versions, tailnet address

## Notes

Phase 4 (hardware) is deliberately after settings: the user asked for OS, user settings, and
default applications first.

**Phase 1 (2026-08-18).** Live run on workstation: MSI PRO Z790-A MAX WIFI (MS-7E07), CachyOS
rolling, kernel 7.1.8-1-cachyos, 1544 packages, 0 pending, `login_shell` `/bin/fish` — the fact
that started this feature, now derived rather than assumed.

`RunResult` deliberately carries **no stderr**. Section data reaches stdout and MCP, and the
surest way never to leak a tool's error output into the envelope is to never hand it to the
caller. A failed probe is simply `ok=False`.

`Runner` exposes `run`, `read` **and** `env`. Sections need to read files (`/etc/os-release`,
`/proc/uptime`, sysfs) as often as they run commands, and over SSH a read is just another
command — so the split belongs in the transport, not in every section.

`pacman -Qu` exits non-zero when nothing is pending. That is the answer "zero", not a failure,
so the count is taken from line count rather than exit status.

**Known limitation — `path_entries` describes tb's process, not the login shell.** The `tb`
wrapper prepends `.venv/bin`, so it appears first in the report. That is the correct answer for
"what will resolve when tb spawns something", and the wrong answer for "what is this machine's
PATH". Capturing a login shell's PATH means spawning one per shell dialect; deferred.

`_render_mapping` in `cli/output.py` gained one level of nesting so section-name → section-dict
renders as titled blocks instead of `str(dict)`. Minimal on purpose; [[rich-output]] supersedes it.

**Phase 3 (2026-08-18).** Phase 2 is deliberately skipped, not forgotten — its boxes stay
unchecked and it is marked deferred in the phase heading. It is blocked on unattended tailnet
SSH, not on anything in this repo.

`_parse_kv` is shared across `/etc/os-release`, `/etc/locale.conf`, `/etc/vconsole.conf` and
`timedatectl show`. systemd emits `KEY=value` everywhere, and every one of those parses more
reliably than the human-facing equivalent — `localectl status` is aligned prose, `locale.conf`
is not. Prefer the machine-readable form even when a status command exists.

Absence is distinguished from failure. A headless host has no `XDG_CURRENT_DESKTOP` and no
`xdg-settings`; both report unset with **no warning**, because that is the correct answer for a
server rather than a broken probe. Only a source that should exist and does not produces a
warning.

Live on workstation: `America/Chicago`, NTP on, `en_US.UTF-8`, keymap `us`, `graphical.target`,
KDE on Wayland. `EDITOR`, `VISUAL` and `PAGER` are all **unset** — anything shelling out to an
editor falls back to whatever it guesses.

**Finding worth acting on:** `default_browser` is `firefox.desktop`, but the `text/html` handler
is `brave-browser.desktop`. Clicking a link and opening an HTML file go to different browsers.
Exactly the kind of drift a baseline exists to surface.

**Phase 4 (2026-08-18).** `cpu` reads `/proc/cpuinfo`, not `lscpu`. cpuinfo's field names are
not localised and its format is identical on every Linux host, so the same parse works over SSH
to a machine whose locale is not ours. `lscpu`'s labels are translated.

**`df` lists every btrfs subvolume separately against one device** — workstation showed the same
3.6 TiB filesystem six times as `/`, `/srv`, `/var/cache`, `/root` and more. Deduped by source
device, keeping the first mount.

Sizes are carried as raw byte counts named `*_bytes` and humanized **only** by the renderer —
the same style of convention as `ok`. Machines get the number, humans get `3.6 TiB`. Binary
units: a 4 TB disk is 3.6 TiB and saying so is the honest answer.

A machine with no GPU reports `gpus: []` with **no warning**. Absent hardware is not a degraded
machine.

`_render_mapping` gained `_is_block`, so a list of dicts nested inside a section (`gpus`,
`disks`, `filesystems`) renders as an indented column table instead of `str(dict)`.

workstation: i7-14700K (28 logical, 20 cores, 1 socket), 62.5 GiB RAM, Samsung SSD 990 PRO 4TB,
**RTX 5070 Ti** — confirming workstation is not a breeze.brain GPU node.

**Phase 5 (2026-08-18).** The seed records **stable facts only**. Uptime, available memory,
pending updates and kernel version all change by the minute; recording them would make every
`tb assets update` report drift that means nothing. There is a test asserting they stay out.

The file has two halves and the split is the feature: `derived` is a command's to write,
`declared` is the human's and no command will ever touch it. The template says so at the top of
every file, because the person editing it six months from now is the one who needs to know.

**Seeding refuses to overwrite.** Inventory is hand-maintained and its git diff *is* the
maintenance log — silently rewriting would destroy the record this repo exists to keep. The
error names the file and says what to do instead.

`--seed` always collects every section regardless of `--section`; a seed built from a subset
would record half a machine.

PyYAML emits the `derived` block rather than hand-formatted text: a vendor string containing a
colon, or a value that is literally `yes`, breaks naively written YAML. The comment header and
`declared` placeholders are hand-written, since no YAML emitter produces comments.

**Feature complete except Phase 2**, which stays deferred on unattended tailnet SSH.

**Phase 6 (2026-08-18).** The baseline was capturing the wrong things. Uptime and available
memory are *system-monitor* data — they change by the minute and belong to a health job. What a
baseline wants is the layer that changes **occasionally and matters when it does**: default
programs, login shell, and interpreter versions. A Python or Node bump breaks things quietly.

`runtimes` probes sixteen interpreters and toolchains. Version flags are not uniform — `go
version` takes no flag, `lua` uses `-v`, `perl --version` is a paragraph whose first line is
blank — so each has its own argv and a single regex takes the first dotted number, which is the
only part consistently present across all of them.

`network` skips loopback and container bridges by name prefix. workstation alone had five docker
bridges; they come and go with the workload, not with the machine. The tailnet address is
reported separately because it is the one this repo addresses machines by.

Inventory now records the tailnet address but **not** LAN addresses — DHCP makes those flap,
while a tailnet address is stable by design.

**SSH split out (2026-08-18).** Remote execution was Phase 2 here and is now [[asset-remote]].
It is a network capability, not a property of describing a machine, and keeping it here left
this feature permanently one phase short of done for a reason that had nothing to do with
baselines. The `Runner` abstraction stays — it is what makes the split cheap.
