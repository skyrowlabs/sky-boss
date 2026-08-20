"""Tests for fleet sections.

Sections take a Runner, so they are tested against a fake one — no subprocess,
no machine-specific assumptions. A section that reached for `subprocess`
directly could not be tested this way, which is the point of the abstraction.
"""

import pytest

from cli.assets import (
    SECTIONS,
    _os_release,
    _parse_kv,
    section_apps,
    section_cpu,
    section_gpu,
    section_memory,
    section_network,
    section_runtimes,
    section_settings,
    section_storage,
    collect,
    section_identity,
    section_os,
    section_shell,
)
from cli.output import Result
from cli.runner import RunResult


class FakeRunner:
    host = "fake"

    def __init__(self, cmds=None, files=None, envs=None):
        self.cmds = cmds or {}
        self.files = files or {}
        self.envs = envs or {}

    def run(self, args, timeout=10):
        key = " ".join(args)
        return RunResult(True, self.cmds[key]) if key in self.cmds else RunResult(False)

    def read(self, path):
        return RunResult(True, self.files[path]) if path in self.files else RunResult(False)

    def env(self, name):
        return RunResult(True, self.envs[name]) if name in self.envs else RunResult(False)


# ---------------------------------------------------------------- os-release


def test_os_release_strips_quotes_and_comments():
    runner = FakeRunner(files={"/etc/os-release": '# a comment\nNAME="CachyOS Linux"\nID=cachyos\n'})
    assert _os_release(runner) == {"NAME": "CachyOS Linux", "ID": "cachyos"}


def test_os_release_missing_file_is_empty_not_an_error():
    assert _os_release(FakeRunner()) == {}


# ---------------------------------------------------------------- identity


def test_identity_reads_dmi_from_sysfs_not_dmidecode():
    """dmidecode needs sudo; sysfs does not. A baseline must never prompt."""
    runner = FakeRunner(
        cmds={"hostname": "workstation\n"},
        files={
            "/sys/class/dmi/id/sys_vendor": "Micro-Star International Co., Ltd.\n",
            "/sys/class/dmi/id/product_name": "MS-7E07\n",
            "/sys/class/dmi/id/board_name": "PRO Z790-A MAX WIFI\n",
        },
    )
    data, warnings = section_identity(runner)
    assert data["hostname"] == "workstation"
    assert data["product"] == "MS-7E07"
    assert warnings == []


def test_identity_missing_sources_warn_but_still_return_data():
    data, warnings = section_identity(FakeRunner())
    assert data["hostname"] is None
    assert data["vendor"] is None
    assert any("hostname" in w for w in warnings)


# ---------------------------------------------------------------- os


def test_os_reports_package_counts():
    runner = FakeRunner(
        files={"/etc/os-release": 'NAME="CachyOS Linux"\nBUILD_ID=rolling\nID=cachyos\n'},
        cmds={
            "uname -r": "7.1.8-1-cachyos\n",
            "uname -m": "x86_64\n",
            "pacman --version": "Pacman v7\n",
            "pacman -Q": "a 1\nb 2\nc 3\n",
            "pacman -Qu": "",
        },
    )
    data, warnings = section_os(runner)
    assert data["distro"] == "CachyOS Linux"
    assert data["version"] == "rolling"
    assert data["kernel"] == "7.1.8-1-cachyos"
    assert data["packages_installed"] == 3
    assert data["updates_pending"] == 0
    assert warnings == []


def test_os_without_pacman_warns_and_leaves_counts_none():
    """A non-Arch host must still report distro and kernel."""
    runner = FakeRunner(
        files={"/etc/os-release": "NAME=Debian\n"},
        cmds={"uname -r": "6.1.0\n"},
    )
    data, warnings = section_os(runner)
    assert data["distro"] == "Debian"
    assert data["packages_installed"] is None
    assert any("pacman" in w for w in warnings)


# ---------------------------------------------------------------- shell


def test_shell_extracts_login_shell_from_passwd():
    """The fact this feature was born from: login shell is fish, not bash."""
    runner = FakeRunner(
        cmds={
            "id -un": "jeston\n",
            "getent passwd jeston": "jeston:x:1000:1000::/home/jeston:/bin/fish\n",
        },
        files={"/etc/shells": "/bin/sh\n/bin/bash\n/bin/fish\n"},
        envs={"PATH": "/home/jeston/.local/bin:/usr/bin"},
    )
    data, warnings = section_shell(runner)
    assert data["login_shell"] == "/bin/fish"
    assert data["path_entries"] == ["/home/jeston/.local/bin", "/usr/bin"]
    assert "/bin/fish" in data["available_shells"]
    assert warnings == []


def test_shell_short_passwd_entry_yields_none():
    runner = FakeRunner(
        cmds={"id -un": "jeston\n", "getent passwd jeston": "truncated:x:1000\n"},
    )
    data, _ = section_shell(runner)
    assert data["login_shell"] is None


# ---------------------------------------------------------------- collect


def test_collect_survives_a_raising_section(monkeypatch):
    """One dead source must not cost you the others."""

    def explode(runner):
        raise RuntimeError("boom")

    monkeypatch.setitem(SECTIONS, "broken", explode)
    result = Result()
    data = collect(FakeRunner(), ["broken", "identity"], result)

    assert "broken" not in data
    assert "identity" in data
    assert result.partial is True
    assert any("section failed" in w for w in result.warnings)


def test_collect_promotes_section_warnings_to_degrade():
    result = Result()
    collect(FakeRunner(), ["identity"], result)
    assert result.partial is True
    assert result.warnings


def test_collect_clean_run_does_not_degrade():
    runner = FakeRunner(
        cmds={"hostname": "h\n"},
        files={
            "/sys/class/dmi/id/sys_vendor": "v\n",
            "/sys/class/dmi/id/product_name": "p\n",
            "/sys/class/dmi/id/board_name": "b\n",
            "/proc/uptime": "1.0 2.0\n",
        },
    )
    result = Result()
    collect(runner, ["identity"], result)
    assert result.partial is False
    assert result.warnings == []


# ---------------------------------------------------------------- settings


def test_settings_parses_systemd_key_value_sources():
    runner = FakeRunner(
        cmds={
            "timedatectl show -p Timezone -p NTP -p LocalRTC": "Timezone=America/Chicago\nLocalRTC=no\nNTP=yes\n",
            "systemctl get-default": "graphical.target\n",
        },
        files={
            "/etc/locale.conf": "LANG=en_US.UTF-8\nLC_TIME=en_US.UTF-8\n",
            "/etc/vconsole.conf": "# written by systemd\nKEYMAP=us\nXKBLAYOUT=us\n",
        },
        envs={"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "wayland"},
    )
    data, warnings = section_settings(runner)
    assert data["timezone"] == "America/Chicago"
    assert data["ntp"] == "yes"
    assert data["locale"] == "en_US.UTF-8"
    assert data["keymap"] == "us"
    assert data["default_target"] == "graphical.target"
    assert data["session_type"] == "wayland"
    assert warnings == []


def test_settings_headless_host_has_no_desktop_and_that_is_not_a_warning():
    """A server has no graphical session. That is an answer, not a fault."""
    runner = FakeRunner(
        cmds={
            "timedatectl show -p Timezone -p NTP -p LocalRTC": "Timezone=UTC\nNTP=yes\n",
            "systemctl get-default": "multi-user.target\n",
        },
        files={"/etc/locale.conf": "LANG=C.UTF-8\n"},
    )
    data, warnings = section_settings(runner)
    assert data["desktop"] is None
    assert data["session_type"] is None
    assert not any("desktop" in w or "session" in w for w in warnings)


def test_settings_warns_when_timedatectl_missing():
    data, warnings = section_settings(FakeRunner())
    assert data["timezone"] is None
    assert any("timedatectl" in w for w in warnings)


# ---------------------------------------------------------------- apps


def test_apps_reads_defaults_and_handlers():
    runner = FakeRunner(
        cmds={
            "xdg-settings get default-web-browser": "firefox.desktop\n",
            "xdg-mime --help": "usage\n",
            "xdg-mime query default text/html": "brave-browser.desktop\n",
            "xdg-mime query default text/plain": "org.kde.kate.desktop\n",
        },
        envs={"EDITOR": "nvim"},
    )
    data, warnings = section_apps(runner)
    assert data["default_browser"] == "firefox.desktop"
    assert data["handlers"]["text/html"] == "brave-browser.desktop"
    assert data["handlers"]["application/pdf"] is None
    assert data["editor"] == "nvim"
    assert data["visual"] is None
    assert warnings == []


def test_apps_absent_tooling_reports_unset_without_warning():
    """Per spec: absent defaults are unset, not a failure."""
    data, warnings = section_apps(FakeRunner())
    assert data["default_browser"] is None
    assert data["handlers"] is None
    assert warnings == []


# ---------------------------------------------------------------- kv parser


def test_parse_kv_skips_comments_and_unquotes():
    parsed = _parse_kv(['# comment', 'A="one"', "B='two'", "C=three", "junk"])
    assert parsed == {"A": "one", "B": "two", "C": "three"}


# ---------------------------------------------------------------- cpu


CPUINFO = """processor\t: 0
model name\t: Intel(R) Core(TM) i7-14700K
cpu cores\t: 20
physical id\t: 0

processor\t: 1
model name\t: Intel(R) Core(TM) i7-14700K
cpu cores\t: 20
physical id\t: 0
"""


def test_cpu_parses_cpuinfo():
    """cpuinfo not lscpu: unlocalised, so the same parse works on a remote host."""
    data, warnings = section_cpu(FakeRunner(files={"/proc/cpuinfo": CPUINFO}))
    assert data["model"] == "Intel(R) Core(TM) i7-14700K"
    assert data["logical"] == 2
    assert data["cores_per_socket"] == 20
    assert data["sockets"] == 1
    assert warnings == []


def test_cpu_missing_cpuinfo_warns():
    data, warnings = section_cpu(FakeRunner())
    assert data["model"] is None
    assert any("cpuinfo" in w for w in warnings)


# ---------------------------------------------------------------- memory


def test_memory_converts_kb_to_bytes():
    runner = FakeRunner(files={"/proc/meminfo": "MemTotal:  1024 kB\nMemAvailable: 512 kB\nSwapTotal: 0 kB\n"})
    data, warnings = section_memory(runner)
    assert data["total_bytes"] == 1024 * 1024
    assert data["swap_total_bytes"] == 0
    # available memory is a live metric, not a baseline fact
    assert "available_bytes" not in data
    assert warnings == []


# ---------------------------------------------------------------- storage


def test_storage_dedupes_btrfs_subvolumes():
    """df lists every btrfs subvolume against one device.

    Without deduping by source a single 4 TB disk appears half a dozen times.
    """
    df_out = (
        "Filesystem Mounted on 1B-blocks Used Avail\n"
        "/dev/nvme0n1p2 / 100 40 60\n"
        "/dev/nvme0n1p2 /srv 100 40 60\n"
        "/dev/nvme0n1p2 /var/cache 100 40 60\n"
        "/dev/nvme0n1p1 /boot 10 1 9\n"
    )
    runner = FakeRunner(
        cmds={
            "lsblk -J -b -d -o NAME,SIZE,TYPE,MODEL":
                '{"blockdevices":[{"name":"nvme0n1","size":400,"type":"disk","model":"Samsung"}]}',
            "df -B1 --output=source,target,size,used,avail -x tmpfs -x devtmpfs -x efivarfs": df_out,
        }
    )
    data, warnings = section_storage(runner)
    assert len(data["filesystems"]) == 2
    assert data["filesystems"][0]["mount"] == "/"
    assert data["filesystems"][0]["size_bytes"] == 100
    assert data["disks"][0]["size_bytes"] == 400
    assert warnings == []


def test_storage_unparseable_lsblk_warns():
    runner = FakeRunner(cmds={"lsblk -J -b -d -o NAME,SIZE,TYPE,MODEL": "not json"})
    _, warnings = section_storage(runner)
    assert any("unparseable" in w for w in warnings)


# ---------------------------------------------------------------- gpu


def test_gpu_absent_is_not_a_warning():
    """A machine with no GPU is not a degraded machine."""
    data, warnings = section_gpu(FakeRunner())
    assert data["gpus"] == []
    assert warnings == []


def test_gpu_parses_csv_and_converts_mib():
    runner = FakeRunner(
        cmds={
            "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits":
                "NVIDIA GeForce RTX 5070 Ti, 16303, 610.57.04\n"
        }
    )
    data, warnings = section_gpu(runner)
    assert data["gpus"][0]["name"] == "NVIDIA GeForce RTX 5070 Ti"
    assert data["gpus"][0]["memory_bytes"] == 16303 * 1024 * 1024
    assert warnings == []


# ---------------------------------------------------------------- inventory seed


import yaml  # noqa: E402

from cli.assets import inventory_record, write_seed  # noqa: E402


BASELINE = {
    "identity": {"hostname": "workstation", "vendor": "MSI", "product": "MS-7E07",
                 "board": "Z790", "uptime_seconds": 20547},
    "os": {"distro": "CachyOS Linux", "kernel": "7.1.8", "updates_pending": 0},
    "cpu": {"model": "i7-14700K", "logical": 28},
    "memory": {"total_bytes": 100, "available_bytes": 50},
    "storage": {"disks": [{"name": "nvme0n1", "size_bytes": 400, "model": "Samsung"}]},
    "gpu": {"gpus": [{"name": "RTX 5070 Ti", "memory_bytes": 1}]},
}


def test_inventory_record_excludes_volatile_facts():
    """Uptime, free memory and pending updates change by the minute.

    Recording them would make every `tb assets update` report drift that means
    nothing.
    """
    record = inventory_record(BASELINE)
    assert record["hostname"] == "workstation"
    assert record["cpu_model"] == "i7-14700K"
    assert record["gpus"] == ["RTX 5070 Ti"]
    for volatile in ("uptime_seconds", "available_bytes", "updates_pending"):
        assert volatile not in record
    # kernel IS recorded — it changes occasionally, and noticing that is the point
    assert record["kernel"] == "7.1.8"


def test_inventory_record_survives_missing_sections():
    record = inventory_record({})
    assert record["hostname"] is None
    assert record["disks"] == []


def test_write_seed_produces_parseable_yaml_with_both_halves(tmp_path):
    path = write_seed(inventory_record(BASELINE), directory=tmp_path)
    assert path.name == "workstation.yaml"

    parsed = yaml.safe_load(path.read_text())
    assert parsed["derived"]["hostname"] == "workstation"
    assert parsed["derived"]["disks"][0]["model"] == "Samsung"
    # declared exists and is entirely empty — every value is the human's to fill
    assert set(parsed["declared"]) == {"role", "purchased", "location", "warranty_end", "notes"}
    assert all(v is None for v in parsed["declared"].values())


def test_write_seed_refuses_to_overwrite(tmp_path):
    """Silently rewriting would destroy the maintenance log the git diff *is*."""
    record = inventory_record(BASELINE)
    write_seed(record, directory=tmp_path)
    with pytest.raises(FileExistsError):
        write_seed(record, directory=tmp_path)


def test_write_seed_quotes_awkward_values(tmp_path):
    """A vendor string with a colon would break hand-written YAML."""
    record = inventory_record(BASELINE) | {"vendor": "Weird: Corp, Ltd.", "product": "yes"}
    path = write_seed(record, directory=tmp_path)
    parsed = yaml.safe_load(path.read_text())
    assert parsed["derived"]["vendor"] == "Weird: Corp, Ltd."
    # unquoted `yes` would parse as boolean True
    assert parsed["derived"]["product"] == "yes"


# ---------------------------------------------------------------- runtimes


def test_runtimes_extracts_versions_from_inconsistent_banners():
    """Every tool formats its banner differently; the number is the constant."""
    runner = FakeRunner(cmds={
        "python3 --version": "Python 3.14.7\n",
        "node --version": "v22.23.2\n",
        "go version": "go version go1.26.5-X:nodwarf5 linux/amd64\n",
        "java --version": "openjdk 26.0.2 2026-07-21\n",
        "lua -v": "Lua 5.5.1  Copyright (C) 1994-2026\n",
    })
    data, warnings = section_runtimes(runner)
    versions = {r["name"]: r["version"] for r in data["installed"]}
    assert versions == {"python": "3.14.7", "node": "22.23.2", "go": "1.26.5",
                        "java": "26.0.2", "lua": "5.5.1"}
    assert warnings == []


def test_runtimes_omits_absent_tools():
    """A machine without Ruby is not missing anything."""
    data, _ = section_runtimes(FakeRunner(cmds={"python3 --version": "Python 3.14.7\n"}))
    assert [r["name"] for r in data["installed"]] == ["python"]


# ---------------------------------------------------------------- network


IP_JSON = """[
 {"ifname":"lo","operstate":"UNKNOWN","addr_info":[{"scope":"host","local":"127.0.0.1"}]},
 {"ifname":"wlan0","operstate":"UP","addr_info":[{"scope":"global","local":"192.0.2.10"}]},
 {"ifname":"docker0","operstate":"DOWN","addr_info":[{"scope":"global","local":"172.17.0.1"}]},
 {"ifname":"br-abc123","operstate":"UP","addr_info":[{"scope":"global","local":"172.20.0.1"}]},
 {"ifname":"tailscale0","operstate":"UNKNOWN","addr_info":[{"scope":"global","local":"100.64.0.1"}]}
]"""


def test_network_skips_loopback_and_container_bridges():
    """Docker bridges come and go with the workload, not with the machine."""
    runner = FakeRunner(cmds={
        "ip -j addr": IP_JSON,
        "tailscale ip -4": "100.64.0.1\n",
        "tailscale status --json": '{"Self":{"DNSName":"device.tailnet-name.ts.net."}}',
    })
    data, warnings = section_network(runner)
    names = [i["name"] for i in data["interfaces"]]
    assert names == ["wlan0", "tailscale0"]
    assert data["tailnet_ip"] == "100.64.0.1"
    # trailing dot stripped
    assert data["tailnet_name"] == "device.tailnet-name.ts.net"
    assert warnings == []


def test_network_unparseable_ip_output_warns():
    _, warnings = section_network(FakeRunner(cmds={"ip -j addr": "not json"}))
    assert any("unparseable" in w for w in warnings)


def test_inventory_records_tailnet_address_but_not_lan():
    """Tailnet addresses are stable by design; DHCP LAN addresses flap."""
    record = inventory_record({
        "network": {"tailnet_ip": "100.64.0.1", "tailnet_name": "device.tailnet-name.ts.net",
                    "interfaces": [{"name": "wlan0", "addresses": ["192.0.2.10"]}]},
        "runtimes": {"installed": [{"name": "python", "version": "3.14.7"}]},
    })
    assert record["tailnet_ip"] == "100.64.0.1"
    assert record["runtimes"] == {"python": "3.14.7"}
    assert "192.0.2.10" not in str(record)
