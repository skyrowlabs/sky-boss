# Ideas List

*Note: This is a list of potential ideas to add. Remove them if once spec'd or shelved*

- ~~watcher for cron jobs~~ — spec'd as [[file-follow]] round 2 (`tb follow --due 15m <path>`);
  the systemd half needs no code, see the doc
- piping commands to claude or other agents -- chaining data into an agent or calling a routine
  and using tb to monitor (how different is this from the tools we have?) — barely different, and
  the arrow points the wrong way: `tb follow -- claude -p …` already works. The version with
  value is exposing tb's observes *to* an agent over MCP, which `--json` purity and the
  `acts` split already make safe
- ~~future runs (non crontab or systemd), tb run --delay=[seconds] [cmd]~~ — spec'd as [[delay]]
- build in embedded scrolling for follow command — reopens [[refresh]] round 2's "a resident
  view is a view"; the chrome band is already the scrollbar, the real cost is a follow/parked
  mode. Canvas already scrolls, so this is terminal-only
- an opt-in `--pty` for follow: one flag answers both things measured 2026-08-22 — a tool's own
  colour (lost because its stdout is a pipe: 6,044 escapes in a terminal, zero under tb) and a
  slow tool's lines stuck in an 8 KB buffer. [[follow]] refuses a pty as the *default*, on the
  grounds that follow is not tmux; opt-in with stated costs is a different question
-
