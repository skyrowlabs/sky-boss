"""tb assets — the home network's machines.

`describe` reports a machine's baseline as independently-degrading sections.
Sections take a :class:`~cli.runner.Runner` and never touch `subprocess`, so the
same code answers for a remote host once `SshRunner` lands.

No section requires sudo: `/sys/class/dmi/id/*` is world-readable, so a baseline
can run unattended as a job.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import rich_click as click

import yaml

from cli.helpers import TB_HOME
from cli.output import Result, emit
from cli.runner import LocalRunner, Runner

# A section returns (data, warnings). Warnings name a source that was absent, so
# the caller can degrade the whole result without the section knowing about it.
SectionResult = tuple[dict, list[str]]


def _parse_kv(lines: list[str]) -> dict[str, str]:
    """KEY=value lines into a dict, unquoted, comments skipped.

    Shared by /etc/os-release, /etc/locale.conf, /etc/vconsole.conf and
    `timedatectl show` — systemd emits this shape everywhere, and every one of
    them parses more reliably than the corresponding human-facing `status`
    output (`localectl status` is aligned prose; locale.conf is not).
    """
    fields: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _os_release(runner: Runner) -> dict[str, str]:
    """Parse /etc/os-release into a plain dict."""
    probe = runner.read("/etc/os-release")
    return _parse_kv(probe.lines()) if probe.ok else {}


# Handlers worth knowing about. Not the whole mimeapps list — those are the ones
# whose misconfiguration is actually felt.
MIME_TYPES = (
    "text/plain",
    "text/html",
    "application/pdf",
    "image/png",
    "inode/directory",
)


def section_identity(runner: Runner) -> SectionResult:
    """Who this machine is, and what hardware it sits in."""
    warnings: list[str] = []

    hostname = runner.run(["hostname"])
    if not hostname.ok:
        warnings.append("identity: hostname unavailable")

    # sysfs rather than dmidecode — readable without sudo.
    dmi = {}
    for field, path in (
        ("vendor", "/sys/class/dmi/id/sys_vendor"),
        ("product", "/sys/class/dmi/id/product_name"),
        ("board", "/sys/class/dmi/id/board_name"),
    ):
        probe = runner.read(path)
        dmi[field] = probe.text if probe.ok else None

    return (
        {
            "hostname": hostname.text if hostname.ok else None,
            "vendor": dmi["vendor"],
            "product": dmi["product"],
            "board": dmi["board"],
        },
        warnings,
    )


def section_os(runner: Runner) -> SectionResult:
    """Distribution, kernel, and package state."""
    warnings: list[str] = []

    release = _os_release(runner)
    if not release:
        warnings.append("os: /etc/os-release unreadable")

    kernel = runner.run(["uname", "-r"])
    arch = runner.run(["uname", "-m"])
    if not kernel.ok:
        warnings.append("os: kernel version unavailable")

    # Package counts are *reported*, never acted on — tb installs nothing.
    installed = pending = None
    have_pacman = runner.run(["pacman", "--version"]).ok
    if have_pacman:
        listing = runner.run(["pacman", "-Q"])
        if listing.ok:
            installed = len(listing.lines())
        updates = runner.run(["pacman", "-Qu"])
        # `pacman -Qu` exits non-zero when nothing is pending, which is not an
        # error — it is the answer "zero".
        pending = len(updates.lines())
    else:
        warnings.append("os: pacman not present; package counts unavailable")

    return (
        {
            "distro": release.get("NAME"),
            "version": release.get("BUILD_ID") or release.get("VERSION_ID"),
            "id": release.get("ID"),
            "kernel": kernel.text if kernel.ok else None,
            "arch": arch.text if arch.ok else None,
            "packages_installed": installed,
            "updates_pending": pending,
        },
        warnings,
    )


def section_shell(runner: Runner) -> SectionResult:
    """Login shell and PATH.

    The login shell is the fact this whole feature was born from: tooling spawns
    bash, the login shell is fish, and a fish function shadows PATH.
    """
    warnings: list[str] = []

    user = runner.run(["id", "-un"])
    login_shell = None
    if user.ok and user.text:
        passwd = runner.run(["getent", "passwd", user.text])
        if passwd.ok and passwd.text:
            parts = passwd.text.split(":")
            login_shell = parts[-1] if len(parts) >= 7 else None
        else:
            warnings.append("shell: passwd entry unavailable")
    else:
        warnings.append("shell: current user unknown")

    shells = runner.read("/etc/shells")
    available = (
        [s for s in shells.lines() if s.startswith("/")] if shells.ok else []
    )
    if not shells.ok:
        warnings.append("shell: /etc/shells unreadable")

    # The PATH of the invoking process, not of a login shell — those differ, and
    # the invoking one is what determines whether `tb` itself resolves.
    path = runner.env("PATH")
    entries = [p for p in path.out.split(":") if p] if path.ok else []
    if not path.ok:
        warnings.append("shell: PATH unavailable")

    return (
        {
            "user": user.text if user.ok else None,
            "login_shell": login_shell,
            "available_shells": available,
            "path_entries": entries,
        },
        warnings,
    )


def section_settings(runner: Runner) -> SectionResult:
    """OS-level settings: time, locale, keyboard, boot target, session."""
    warnings: list[str] = []

    time_probe = runner.run(["timedatectl", "show", "-p", "Timezone", "-p", "NTP", "-p", "LocalRTC"])
    time_fields = _parse_kv(time_probe.lines()) if time_probe.ok else {}
    if not time_probe.ok:
        warnings.append("settings: timedatectl unavailable")

    locale_probe = runner.read("/etc/locale.conf")
    locale_fields = _parse_kv(locale_probe.lines()) if locale_probe.ok else {}
    if not locale_probe.ok:
        warnings.append("settings: /etc/locale.conf unreadable")

    vconsole = runner.read("/etc/vconsole.conf")
    vconsole_fields = _parse_kv(vconsole.lines()) if vconsole.ok else {}

    target = runner.run(["systemctl", "get-default"])
    if not target.ok:
        warnings.append("settings: systemd default target unavailable")

    # A headless host has no desktop session. That is an answer, not a fault, so
    # it reports as unset without a warning.
    desktop = runner.env("XDG_CURRENT_DESKTOP")
    session = runner.env("XDG_SESSION_TYPE")

    return (
        {
            "timezone": time_fields.get("Timezone"),
            "ntp": time_fields.get("NTP"),
            "local_rtc": time_fields.get("LocalRTC"),
            "locale": locale_fields.get("LANG"),
            "keymap": vconsole_fields.get("KEYMAP"),
            "default_target": target.text if target.ok else None,
            "desktop": desktop.text or None if desktop.ok else None,
            "session_type": session.text or None if session.ok else None,
        },
        warnings,
    )


def section_apps(runner: Runner) -> SectionResult:
    """Default applications.

    Absent defaults report as unset rather than failing — a headless host has no
    xdg-settings at all, and that is expected, not broken.
    """
    browser = runner.run(["xdg-settings", "get", "default-web-browser"])

    handlers: dict[str, str | None] = {}
    if runner.run(["xdg-mime", "--help"]).ok:
        for mime in MIME_TYPES:
            probe = runner.run(["xdg-mime", "query", "default", mime])
            handlers[mime] = probe.text if probe.ok and probe.text else None

    env_apps = {}
    for name in ("EDITOR", "VISUAL", "PAGER"):
        probe = runner.env(name)
        env_apps[name.lower()] = probe.text or None if probe.ok else None

    return (
        {
            "default_browser": browser.text if browser.ok and browser.text else None,
            **env_apps,
            "handlers": handlers or None,
        },
        [],
    )


def section_cpu(runner: Runner) -> SectionResult:
    """Processor, from /proc/cpuinfo.

    cpuinfo rather than lscpu: its field names are not localised and its format
    is identical on every Linux host, so the same parse works over SSH to a
    machine whose locale is not ours.
    """
    warnings: list[str] = []
    probe = runner.read("/proc/cpuinfo")
    if not probe.ok:
        return ({"model": None, "logical": None, "cores_per_socket": None, "sockets": None},
                ["cpu: /proc/cpuinfo unreadable"])

    model = None
    logical = 0
    cores_per_socket = None
    sockets: set[str] = set()
    for line in probe.lines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "model name" and model is None:
            model = value
        elif key == "processor":
            logical += 1
        elif key == "cpu cores" and cores_per_socket is None:
            cores_per_socket = int(value) if value.isdigit() else None
        elif key == "physical id":
            sockets.add(value)

    return (
        {
            "model": model,
            "logical": logical or None,
            "cores_per_socket": cores_per_socket,
            "sockets": len(sockets) or None,
        },
        warnings,
    )


def section_memory(runner: Runner) -> SectionResult:
    """RAM and swap. /proc/meminfo reports kB; the envelope carries bytes."""
    probe = runner.read("/proc/meminfo")
    if not probe.ok:
        return ({"total_bytes": None, "swap_total_bytes": None},
                ["memory: /proc/meminfo unreadable"])

    fields: dict[str, int] = {}
    for line in probe.lines():
        key, _, value = line.partition(":")
        parts = value.split()
        if parts and parts[0].isdigit():
            fields[key.strip()] = int(parts[0]) * 1024  # kB -> bytes

    return (
        {
            "total_bytes": fields.get("MemTotal"),
            "swap_total_bytes": fields.get("SwapTotal"),
        },
        [],
    )


def section_storage(runner: Runner) -> SectionResult:
    """Physical disks and mounted filesystems."""
    warnings: list[str] = []

    disks = []
    lsblk = runner.run(["lsblk", "-J", "-b", "-d", "-o", "NAME,SIZE,TYPE,MODEL"])
    if lsblk.ok:
        try:
            for dev in json.loads(lsblk.out).get("blockdevices", []):
                if dev.get("type") == "disk":
                    disks.append(
                        {"name": dev.get("name"), "size_bytes": dev.get("size"), "model": dev.get("model")}
                    )
        except (json.JSONDecodeError, AttributeError):
            warnings.append("storage: lsblk output unparseable")
    else:
        warnings.append("storage: lsblk unavailable")

    # df lists every btrfs subvolume separately against one device, so dedupe by
    # source — otherwise a single 4 TB disk appears half a dozen times.
    filesystems = []
    df = runner.run(["df", "-B1", "--output=source,target,size,used,avail",
                     "-x", "tmpfs", "-x", "devtmpfs", "-x", "efivarfs"])
    if df.ok:
        seen: set[str] = set()
        for line in df.lines()[1:]:
            parts = line.split()
            if len(parts) < 5 or parts[0] in seen:
                continue
            seen.add(parts[0])
            try:
                filesystems.append({
                    "source": parts[0],
                    "mount": parts[1],
                    "size_bytes": int(parts[2]),
                    "used_bytes": int(parts[3]),
                    "avail_bytes": int(parts[4]),
                })
            except ValueError:
                continue
    else:
        warnings.append("storage: df unavailable")

    return ({"disks": disks or None, "filesystems": filesystems or None}, warnings)


def section_gpu(runner: Runner) -> SectionResult:
    """NVIDIA GPUs.

    A machine with no GPU is not a degraded machine — absent nvidia-smi reports
    an empty list with no warning.
    """
    probe = runner.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
         "--format=csv,noheader,nounits"]
    )
    if not probe.ok:
        return ({"gpus": []}, [])

    gpus = []
    for line in probe.lines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        gpus.append({
            "name": parts[0],
            # nvidia-smi reports MiB with nounits.
            "memory_bytes": int(parts[1]) * 1024 * 1024 if parts[1].isdigit() else None,
            "driver": parts[2],
        })

    return ({"gpus": gpus}, [])


# Container and virtual bridges are infrastructure that comes and goes with the
# workload — workstation alone had five docker bridges. A baseline wants the
# machine's own addresses.
SKIP_INTERFACES = ("lo", "docker", "br-", "veth", "virbr")

# Version flags are not uniform: `go version` takes no flag, lua uses -v, and
# `perl --version` is a paragraph whose first line is blank.
RUNTIME_PROBES: tuple[tuple[str, list[str]], ...] = (
    ("python", ["python3", "--version"]),
    ("node", ["node", "--version"]),
    ("npm", ["npm", "--version"]),
    ("deno", ["deno", "--version"]),
    ("bun", ["bun", "--version"]),
    ("ruby", ["ruby", "--version"]),
    ("go", ["go", "version"]),
    ("rustc", ["rustc", "--version"]),
    ("cargo", ["cargo", "--version"]),
    ("java", ["java", "--version"]),
    ("perl", ["perl", "-e", "print substr($^V,1)"]),
    ("php", ["php", "--version"]),
    ("lua", ["lua", "-v"]),
    ("gcc", ["gcc", "--version"]),
    ("clang", ["clang", "--version"]),
    ("git", ["git", "--version"]),
)

_VERSION = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _extract_version(text: str) -> str | None:
    """First dotted number in the output.

    Every tool formats its banner differently — `v22.23.2`, `go version go1.26.5
    linux/amd64`, `openjdk 26.0.2 2026-07-21`. The number is the only part worth
    keeping and the only part that is consistently there.
    """
    match = _VERSION.search(text)
    return match.group(1) if match else None


def section_runtimes(runner: Runner) -> SectionResult:
    """Interpreters and toolchains, with versions.

    This is the layer that changes occasionally and matters when it does — a
    Python or Node bump breaks things quietly. Absent tools are omitted rather
    than listed as null: a machine without Ruby is not missing anything.
    """
    found = []
    for name, args in RUNTIME_PROBES:
        probe = runner.run(args, timeout=5)
        if not probe.ok:
            continue
        version = _extract_version(probe.text.splitlines()[0] if probe.text else "")
        if version:
            found.append({"name": name, "version": version})
    return ({"installed": found}, [])


def section_network(runner: Runner) -> SectionResult:
    """Addresses this machine answers on."""
    warnings: list[str] = []

    interfaces = []
    probe = runner.run(["ip", "-j", "addr"])
    if probe.ok:
        try:
            for iface in json.loads(probe.out):
                name = iface.get("ifname", "")
                if name.startswith(SKIP_INTERFACES):
                    continue
                addrs = [
                    a.get("local")
                    for a in iface.get("addr_info") or []
                    if a.get("scope") == "global" and a.get("local")
                ]
                interfaces.append(
                    {"name": name, "state": iface.get("operstate"), "addresses": addrs or None}
                )
        except (json.JSONDecodeError, AttributeError, TypeError):
            warnings.append("network: ip output unparseable")
    else:
        warnings.append("network: ip unavailable")

    tailnet_ip = runner.run(["tailscale", "ip", "-4"])
    tailnet_name = runner.run(["tailscale", "status", "--json"])
    dns_name = None
    if tailnet_name.ok:
        try:
            dns_name = (json.loads(tailnet_name.out).get("Self") or {}).get("DNSName")
            dns_name = dns_name.rstrip(".") if dns_name else None
        except (json.JSONDecodeError, AttributeError):
            pass

    return (
        {
            "interfaces": interfaces or None,
            "tailnet_ip": tailnet_ip.text if tailnet_ip.ok and tailnet_ip.text else None,
            "tailnet_name": dns_name,
        },
        warnings,
    )


SECTIONS: dict[str, Callable[[Runner], SectionResult]] = {
    "identity": section_identity,
    "os": section_os,
    "shell": section_shell,
    "settings": section_settings,
    "apps": section_apps,
    "cpu": section_cpu,
    "memory": section_memory,
    "storage": section_storage,
    "gpu": section_gpu,
    "runtimes": section_runtimes,
    "network": section_network,
}


INVENTORY_DIR = TB_HOME / "inventory"

# The seed keeps only *stable* facts. Uptime, available memory and pending
# updates all change by the minute; recording them would make every `tb assets
# update` report drift that means nothing.
def inventory_record(data: dict) -> dict:
    """The subset of a baseline worth recording as a system of record.

    Two kinds of fact qualify: hardware identity, which barely changes, and the
    **software layer that changes occasionally and matters when it does** —
    kernel, login shell, default browser, interpreter versions. A Python or Node
    bump breaks things quietly, and noticing it is the point.

    Live metrics are excluded by design. There is no uptime, no free memory, no
    pending-update count: those change by the minute and would make every
    `tb assets update` report drift that means nothing. Machine health is a job
    (see docs/jobs-backlog.md), not a baseline.

    LAN addresses are excluded too — DHCP makes them flap. The tailnet address
    is stable by design, so that one is recorded.
    """
    identity = data.get("identity") or {}
    os_info = data.get("os") or {}
    cpu = data.get("cpu") or {}
    memory = data.get("memory") or {}
    storage = data.get("storage") or {}
    gpu = data.get("gpu") or {}
    shell = data.get("shell") or {}
    apps = data.get("apps") or {}
    runtimes = data.get("runtimes") or {}
    network = data.get("network") or {}

    return {
        "hostname": identity.get("hostname"),
        "tailnet_ip": network.get("tailnet_ip"),
        "tailnet_name": network.get("tailnet_name"),
        "vendor": identity.get("vendor"),
        "product": identity.get("product"),
        "board": identity.get("board"),
        "distro": os_info.get("distro"),
        "kernel": os_info.get("kernel"),
        "login_shell": shell.get("login_shell"),
        "default_browser": apps.get("default_browser"),
        "cpu_model": cpu.get("model"),
        "cpu_logical": cpu.get("logical"),
        "memory_total_bytes": memory.get("total_bytes"),
        "disks": [
            {"name": d.get("name"), "size_bytes": d.get("size_bytes"), "model": d.get("model")}
            for d in (storage.get("disks") or [])
        ],
        "gpus": [g.get("name") for g in (gpu.get("gpus") or [])],
        "runtimes": {r["name"]: r["version"] for r in (runtimes.get("installed") or [])},
    }


SEED_HEADER = """# tackle-box machine record — {hostname}
#
# derived   Facts a command can answer. Written by `tb assets describe --seed`.
#           Do not hand-edit — your edits are what the next refresh overwrites.
#
# declared  Facts nothing can derive. Yours alone. No command will ever write,
#           reorder, or reformat this block. The git diff of these files is the
#           maintenance log, so record the *why* inline as a field comment.

"""

DECLARED_BLOCK = """
declared:
  role:           # what this machine is for
  purchased:      # YYYY-MM-DD
  location:       # where it physically lives
  warranty_end:   # YYYY-MM-DD
  notes:          # anything a command cannot answer
"""


def write_seed(record: dict, directory: Path | None = None) -> Path:
    """Write a new inventory file. Never overwrites.

    Refusing is deliberate: inventory is hand-maintained and its git diff is the
    maintenance log, so silently rewriting a file would destroy the record this
    repo exists to keep.
    """
    directory = directory or INVENTORY_DIR
    hostname = record.get("hostname") or "unknown-host"
    path = directory / f"{hostname}.yaml"

    if path.exists():
        raise FileExistsError(path)

    directory.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump({"derived": record}, sort_keys=False, default_flow_style=False)
    path.write_text(SEED_HEADER.format(hostname=hostname) + body + DECLARED_BLOCK)
    return path


# Which section each inventory field is derived from. `--section` filters the
# comparison through this: a field whose source section was not collected is
# skipped, never reported as drift against nothing.
FIELD_SECTION: dict[str, str] = {
    "hostname": "identity",
    "vendor": "identity",
    "product": "identity",
    "board": "identity",
    "tailnet_ip": "network",
    "tailnet_name": "network",
    "distro": "os",
    "kernel": "os",
    "login_shell": "shell",
    "default_browser": "apps",
    "cpu_model": "cpu",
    "cpu_logical": "cpu",
    "memory_total_bytes": "memory",
    "disks": "storage",
    "gpus": "gpu",
    "runtimes": "runtimes",
}


def _summarize_list(items: list) -> str | None:
    """A list as one order-stable string.

    Sorted, so a kernel reordering `disks` is not reported as drift. Comparing
    lists positionally would make every reboot look like a hardware change.
    """
    if not items:
        return None
    if all(isinstance(i, dict) for i in items):
        parts = []
        for item in sorted(items, key=lambda d: str(d.get("name", ""))):
            rest = [f"{k}={v}" for k, v in sorted(item.items()) if k != "name" and v is not None]
            name = item.get("name")
            parts.append(f"{name}({', '.join(rest)})" if rest else str(name))
        return "; ".join(parts)
    return ", ".join(sorted(str(i) for i in items))


def flatten_record(record: dict) -> dict[str, object]:
    """Inventory fields as comparable leaves.

    Nested dicts flatten one level — `runtimes.python` rather than the whole
    `runtimes` map — so a Python bump names Python instead of dumping every
    interpreter as one changed blob.
    """
    flat: dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            for sub, sub_value in sorted(value.items()):
                flat[f"{key}.{sub}"] = sub_value
        elif isinstance(value, list):
            flat[key] = _summarize_list(value)
        else:
            flat[key] = value
    return flat


def load_inventory(hostname: str, directory: Path | None = None) -> dict | None:
    """The recorded derived block, or None if this host has no record."""
    path = (directory or INVENTORY_DIR) / f"{hostname}.yaml"
    if not path.exists():
        return None
    parsed = yaml.safe_load(path.read_text()) or {}
    return parsed.get("derived") or {}


def compare_record(recorded: dict, current: dict, sections: set[str] | None = None) -> list[dict]:
    """Drift between a recorded and a freshly derived record.

    Compares the union of both key sets, so a field that disappeared is drift
    just as much as one that changed.
    """
    old = flatten_record(recorded)
    new = flatten_record(current)

    rows = []
    for field in sorted(set(old) | set(new)):
        if sections is not None:
            source = FIELD_SECTION.get(field.split(".", 1)[0])
            if source is not None and source not in sections:
                continue
        before, after = old.get(field), new.get(field)
        if before != after:
            rows.append({"field": field, "recorded": before, "current": after})
    return rows


def rewrite_derived(path: Path, record: dict) -> None:
    """Replace the `derived:` block in place, touching nothing else.

    Textual surgery, not a YAML round-trip. Loading and re-dumping the whole
    file would discard every comment — including the `declared:` placeholders
    and any note the operator wrote next to a field, which is the maintenance
    log this repo keeps. The block is anchored on top-level keys (column zero),
    so everything before `derived:` and from the next top-level key onward is
    preserved byte for byte.

    Comments *inside* the derived block are not preserved. That block is
    machine-written and says so.
    """
    lines = path.read_text().splitlines(keepends=True)

    start = next((i for i, line in enumerate(lines) if line.startswith("derived:")), None)
    if start is None:
        raise ValueError(f"{path} has no derived: block")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].rstrip("\n")
        # A top-level key: no indentation, not a comment, not blank.
        if stripped and not stripped[0].isspace() and not stripped.startswith("#"):
            end = i
            break

    block = yaml.safe_dump({"derived": record}, sort_keys=False, default_flow_style=False)
    path.write_text("".join(lines[:start]) + block + "".join(lines[end:]))


def collect(runner: Runner, names: list[str], result: Result) -> dict:
    """Run each named section, degrading rather than aborting on failure.

    One dead source must never cost you the other eleven, so a section that
    raises is recorded and skipped — the rest still run.
    """
    data: dict = {}
    for name in names:
        try:
            section_data, warnings = SECTIONS[name](runner)
        except Exception as exc:  # noqa: BLE001 — a bad section must not kill the run
            result.degrade(f"{name}: section failed ({exc.__class__.__name__})")
            continue
        data[name] = section_data
        for warning in warnings:
            result.degrade(warning)
    return data


# ============================================================================
# Bodies — read and write, split along the line the taxonomy draws
#
# Reading this machine and reading its record are `info`. Comparing the two is a
# `check`. Rewriting the record is a write, and therefore reachable only through
# `tb run` — which is why these are plain functions rather than commands with an
# --apply flag. The flag was the seam.
# ============================================================================


SECTION_OPTION = click.option(
    "--section",
    "section_names",
    multiple=True,
    type=click.Choice(sorted(SECTIONS)),
    # metavar + choices in the help text: the inline choice list has no spaces,
    # so at 80 columns rich-click breaks it mid-word.
    metavar="NAME",
    help="Limit to one or more sections. Repeatable. Default: all. "
    f"Sections: {', '.join(sorted(SECTIONS))}.",
)


def describe_machine(section_names: tuple[str, ...] = ()) -> Result:
    """This machine's baseline, derived fresh. Reads only."""
    result = Result()
    result.data = collect(LocalRunner(), list(section_names) or list(SECTIONS), result)
    return result


def _current_and_recorded(section_names: tuple[str, ...]) -> tuple[Result, dict, dict, str] | Result:
    """Collect this machine and load its record, or return the failure envelope.

    Shared by the drift check and the refresh task so the two can never disagree
    about what "the record" is.
    """
    requested = set(section_names) if section_names else None
    # identity is always collected: the hostname is how the record is found.
    names = sorted({"identity", *(requested or set(SECTIONS))})

    result = Result()
    data = collect(LocalRunner(), names, result)
    current = inventory_record(data)

    hostname = current.get("hostname")
    if not hostname:
        return Result(ok=False, data={"error": "could not determine hostname"})

    recorded = load_inventory(hostname)
    if recorded is None:
        return Result(
            ok=False,
            data={
                "error": f"no inventory record for {hostname}",
                "hint": "seed one first: tb run asset-seed",
            },
        )
    return result, current, recorded, hostname


def check_drift(section_names: tuple[str, ...] = ()) -> Result:
    """Re-derive this machine and report drift against its inventory record.

    Reads only — both the machine and the record. Applying the drift is
    `tb run asset-refresh`, and that separation is deliberate: the git diff of
    `inventory/` is the maintenance log, so a timer that silently rewrote the
    record would erase the very history the file exists to keep.
    """
    loaded = _current_and_recorded(section_names)
    if isinstance(loaded, Result):
        return loaded
    result, current, recorded, hostname = loaded

    requested = set(section_names) if section_names else None
    drift = compare_record(recorded, current, requested)
    for row in drift:
        result.degrade(f"{row['field']}: {row['recorded']} -> {row['current']}")

    result.data = {
        "host": hostname,
        "fields_compared": len(flatten_record(current)) if requested is None else None,
        "drift": drift,
    }
    return result


def seed_inventory() -> Result:
    """Write the first inventory record for this machine. Refuses to overwrite.

    A seed built from a subset would record half a machine, so this always
    collects everything.
    """
    result = Result()
    data = collect(LocalRunner(), list(SECTIONS), result)
    try:
        path = write_seed(inventory_record(data))
    except FileExistsError as exc:
        return Result(
            ok=False,
            data={
                "error": f"{Path(str(exc)).name} already exists",
                "hint": "inventory is hand-maintained; remove the file to re-seed, "
                "or reconcile with tb run asset-refresh once it exists",
            },
        )
    # Relative to TB_HOME, not the repo — the file lives in your home now, and
    # relative_to() raises rather than degrades when the path is not underneath.
    result.data = {"seeded": str(path.relative_to(TB_HOME)), **data}
    return result


def refresh_inventory(section_names: tuple[str, ...] = ()) -> Result:
    """Rewrite the derived block with current reality. Declared fields untouched.

    Updates tb's record of the machine, never the machine. Nothing is installed,
    upgraded, or restarted.
    """
    loaded = _current_and_recorded(section_names)
    if isinstance(loaded, Result):
        return loaded
    result, current, recorded, hostname = loaded

    requested = set(section_names) if section_names else None
    drift = compare_record(recorded, current, requested)
    for row in drift:
        result.warn(f"{row['field']}: {row['recorded']} -> {row['current']}")

    applied = False
    if drift:
        # A scoped run re-derives only some sections, so writing `current`
        # wholesale would blank every field it did not look at. Merge instead.
        merged = {**recorded, **{k: v for k, v in current.items()
                                 if requested is None
                                 or FIELD_SECTION.get(k) in requested
                                 or FIELD_SECTION.get(k) is None}}
        rewrite_derived(INVENTORY_DIR / f"{hostname}.yaml", merged)
        applied = True

    result.data = {"host": hostname, "applied": applied, "drift": drift}
    return result


# ============================================================================
# Commands — registered by cli/info.py and cli/check.py, not here
# ============================================================================


@click.command(name="assets")
@SECTION_OPTION
@emit
def assets_info(section_names: tuple[str, ...]) -> Result:
    """Report this machine's baseline."""
    return describe_machine(section_names)


@click.command(name="drift")
@SECTION_OPTION
@emit
def drift(section_names: tuple[str, ...]) -> Result:
    """Compare this machine against its inventory record."""
    return check_drift(section_names)
