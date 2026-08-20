# Jobs backlog

Candidate jobs for `tb auto`. Not features — this is the pool that feature specs get drawn
from. Add freely; promote to a feature doc only when a job is next up.

**D** = deterministic script (a correct answer a script can compute).
**A** = agentic (needs judgment). Prefer D. Reach for A when the task genuinely needs
interpretation, not because prompting is faster to write.

Homebase-level only. jam.sense's `jam report` jobs are not listed and are not ours — see
CLAUDE.md § Boundary.

## Fleet / machine health

| Job | Kind | Notes |
|---|---|---|
| Tailnet reachability sweep | D | 6 nodes as of 2026-08-18; `laptop` was already offline during the first survey |
| Disk space + SMART across fleet | D | |
| Pending updates + reboot-required | D | `pacman -Qu` on Arch hosts, apt on the Pi |
| Docker container health | D | 11 containers on workstation alone |
| Dangling image / volume reclaim | D | Reclaims real disk on a GPU box |
| New-device-on-LAN detection | D | Needs a baseline snapshot first |
| Load / temp / uptime rollup | D | Feeds `tb brief` |
| Temperature / sensor readings | D | `sensors` is installed. Parked: deliberately excluded from `tb assets describe`, which is a baseline, not health |

## Backup / data

Requires `restic` + `rclone` — neither installed as of 2026-08-18 (only `rsync`).
Dropbox and Google Drive are **sync, not backup**: they propagate deletion and corruption.
Use them as the offsite destination for encrypted restic snapshots, never as the mechanism.

| Job | Kind | Notes |
|---|---|---|
| restic backup — HA config | D | The crown jewel; hours of pairing/tuning that exists in one place. Blocked on the Pi |
| restic backup — inventory + fleet config | D | |
| `restic check` integrity verify | D | Cheap; catches silent repo corruption |
| **Restore drill** | D | Restore to scratch, compare, report. Turns "a backup exists" into "I can recover" |
| Offsite freshness check | D | Is the Dropbox/GDrive copy actually current |
| Unpushed / uncommitted work audit | D | Across `~/src`; catches work living only on one disk |

## Home automation

All blocked on the HA Pi being up and on the tailnet. HA availability gates the rest.

| Job | Kind | Notes |
|---|---|---|
| HA availability check | D | First one; everything else depends on it |
| Lab temp/humidity thresholds | D | Near `host-2` — 4x 145W in a residential room |
| Alarm armed-state + sensors → brief | D | **Read-only.** Never arm/disarm/unlock — see CLAUDE.md § Home automation |
| Smart-device battery sweep | D | Dead sensor batteries are silent failures |
| Night-purge / climate decision | A | Rehearsal for breeze.brain's passive-cooling thesis at house scale |

## Cross-tool / reporting

| Job | Kind | Notes |
|---|---|---|
| `doctor` — auth expiry across CLIs | D | aws, bws, gh, stripe, tailscale. Each keeps its own auth |
| Open PRs + failing checks | D | via `gh` |
| AWS spend snapshot | D | |
| **Daily brief** | A | Agentic synthesis over deterministic inputs |

## Housekeeping / agentic

| Job | Kind | Notes |
|---|---|---|
| tb log rotation + ledger pruning | D | Or the ledger grows forever |
| Weekly homebase review — what's drifting | A | |
| Inventory reconciliation | A | Does `inventory/*.yaml` match what is actually on the network |
| Incident triage | A | Diagnose and propose. Does not act |

## First three

1. **Tailnet reachability sweep** — trivial, exercises the runner end to end, useful immediately.
2. **Unpushed / uncommitted work audit** — pure local, no dependencies, catches real risk today.
3. **restic backup + restore drill** — the pair the job runner exists for. Forces a remote
   target, a real failure mode, and a verification step.
