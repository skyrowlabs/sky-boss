---
slug: asset-remote
title: Reaching the fleet — discovery and remote execution
status: draft
created: 2026-08-18
updated: 2026-08-18
agent_value: 3
key_files: []
---

# Reaching the fleet — discovery and remote execution

## Why

[[machine-baseline]] can describe *this* machine. It cannot describe any other, because nothing
in this repo can yet reach one.

That is a network capability, not a property of describing a machine — which is why it was split
out. Every command that wants to act across the home network needs the same three things:
knowing which hosts exist, knowing which are reachable, and running something on one. Building
that once, behind the `Runner` interface the baseline already uses, means no section and no
future command has to care where it runs.

## Shape

Three layers, each useful on its own.

**Discovery.** `tailscale status --json` reports `HostName`, `OS` and `Online` for every node,
which is enough to derive the addressable set without any configuration file to maintain. Android
nodes are on the tailnet but are not hosts you can run commands on; the describable set is the
online Linux ones. As of 2026-08-18: `workstation` (self), `gpu-node`, `gpu-hub`, with
`laptop` offline.

**Transport.** `SshRunner` implements the same `Runner` protocol as `LocalRunner` — `run`, `read`,
`env`. A `read` over SSH is just another command. Because sections were written against the
protocol and never against `subprocess`, every existing section works remotely with no change.

**Targeting.** `--host <name>` and `--all` on commands that accept them, starting with
`tb assets describe`.

Hard rules for the transport:

- **Never interactive.** `BatchMode=yes`, an explicit `ConnectTimeout`, and a hard wall-clock
  timeout. A prompt that blocks forever is the failure mode this must not have, because these
  commands are meant to run unattended as jobs.
- **Machines are addressed by tailnet name or address**, never LAN IP — DHCP makes those flap.
- **Offline, unreachable, and auth-required are three different answers** and each degrades with
  its own message. "Cannot reach" and "will not authenticate" need different fixes.
- **Remote hosts are read-only.** Nothing is installed, written, or restarted on another machine.

**Does not do:**

- No fan-out writes, no configuration management, no remote package installation. This reaches
  machines to *read* them.
- No LAN scanning or new-device detection. Those are jobs (see `docs/jobs-backlog.md`) and can
  build on discovery once it exists.
- No credential management. SSH keys are the operator's to place; `tb` never handles them.
- No agent or daemon on remote hosts. Plain SSH to what is already there.

## Prerequisite: unattended SSH does not work today

Probed 2026-08-18 with `BatchMode=yes`:

- **`gpu-node`** — Tailscale SSH answers "requires an additional check … visit
  https://login.tail…". Browser re-auth is what the feature is *for* and cannot be satisfied
  unattended. This is not a misconfiguration.
- **`gpu-hub`** — connects far enough to emit a key-exchange warning, then hangs until
  killed at 10s.
- **`laptop`** — offline, connection timed out. Correct behaviour, nothing to fix.

**Plain SSH keys over the tailnet are the durable answer for jobs.** Tailscale SSH's check period
is designed for human sessions; a scheduled run will keep failing it. Phase 2 can be built and
unit-tested against fakes without this, but cannot be verified end-to-end until one host accepts
key-based non-interactive SSH.

## Phases

### Phase 1 — Discovery

- [ ] Parse `tailscale status --json` into a host list: name, OS, online, tailnet address
- [ ] Filter to addressable hosts (online, Linux, not self)
- [ ] `tb assets hosts` listing them, using the `ok` convention so online/offline reads as status
- [ ] Degrade cleanly when tailscale is absent or logged out

### Phase 2 — SSH transport

- [ ] `SshRunner` implementing `Runner` — `run`, `read`, `env`
- [ ] `BatchMode=yes`, `ConnectTimeout`, hard wall-clock timeout, never interactive
- [ ] Offline, unreachable and auth-required degrade with distinct messages
- [ ] Unit-tested against a fake transport, so it is testable before SSH auth is fixed
- [ ] Secret-containment test across the SSH path

### Phase 3 — Remote targeting

- [ ] `--host <name>` and `--all` on `tb assets describe`
- [ ] One unreachable host degrades without costing the others
- [ ] Per-host inventory seeding
- [ ] End-to-end verification against a real host *(blocked on the prerequisite above)*

## Notes

Split out of [[machine-baseline]] on 2026-08-18. It had been Phase 2 there, which left that
feature permanently one phase short of done for a reason that had nothing to do with baselines.

The `Runner` protocol already exists and is the reason this is cheap: sections never call
`subprocess`, so they inherit remote execution without being touched.
