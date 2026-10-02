# In-Flight Reports

Each file here describes the **current window**: `<latest release tag>..HEAD`.
A release closes the window and freezes the edition under
[`../releases/`](../releases/README.md).

The window is resolved from one place — `scripts/docs/release_window.py` — and
stamped onto every report as frontmatter plus a prose line under the H1.
`dev check reports` validates every anchor and blocks CI.

| Report | Cadence | Produced by |
| ------ | ------- | ----------- |
|        |         |             |

<!-- SCAFFOLD: one row per scheduled report. A report with no owner here is one
     that is refreshed by hand or never — the exact condition anchoring exists
     to make visible. -->

**Cadence did not change when anchoring landed.** A weekly job still runs
weekly; only the window it describes moved from "since this last ran" to "since
the last release". Never defer a scheduled report until a release is cut.
