# Ideas List

*Note: This is a list of potential ideas to add. Remove them if once spec'd or shelved*

- ~~watcher for cron jobs~~ — spec'd as [[file-follow]] round 2 (`tb follow --due 15m <path>`);
  the systemd half needs no code, see the doc
- ~~piping commands to claude or other agents~~ — answered: chaining needs nothing (`tb follow
  -- claude -p …` already works, and a pipeline is a shell pipe). The inverse is spec'd as
  [[mcp]] — the toolbox offered to an agent over stdio
- ~~future runs (non crontab or systemd), tb run --delay=[seconds] [cmd]~~ — spec'd as [[delay]]
- build in embedded scrolling for follow command — reopens [[refresh]] round 2's "a resident
  view is a view"; the chrome band is already the scrollbar, the real cost is a follow/parked
  mode. Canvas already scrolls, so this is terminal-only
- an opt-in `--pty` for follow: one flag answers both things measured 2026-08-22 — a tool's own
  colour (lost because its stdout is a pipe: 6,044 escapes in a terminal, zero under tb) and a
  slow tool's lines stuck in an 8 KB buffer. [[follow]] refuses a pty as the *default*, on the
  grounds that follow is not tmux; opt-in with stated costs is a different question
- ~~a log analyzer / view setup utility~~ — answered: lnav 0.14.0 headless already emits JSON
  (`lnav -n -q -c ';SELECT …' -c ':write-json-to -'`), so it is a `tb data --from json --` source
  and a saved tool, not a new command. Measured 2026-08-23
- ~~a richer result header (type, dimensions, size, modified, END OF DATA)~~ — split by owner:
  type and dimensions are in-band, spec'd as [[table-views]] round 4; the band and the terminator
  are out-of-band, spec'd as [[chrome]] round 3. `size`/`modified` were already on chrome's file
  cursor row. The leading `|` gutter is rejected — it breaks copy-paste and `tb read` is verbatim
  by contract
- ~~a centralized system to manage how six projects' agents work~~ — spec'd as [[roll-call]]
- `--cols` naming a column that does not exist renders a column of dashes rather than saying so.
  The same silence [[table-views]] round 4 was opened for, one level along: the flag *was* applied,
  it just named nothing. Found while verifying [[roll-call]] round 1 against real data
- two table tests inherit the ambient terminal width instead of pinning one, so they fail at 40 and
  at 200 columns while passing at 80 — `test_a_detail_column_gets_its_own_line_under_the_record`
  and `test_a_column_that_did_not_fit_is_reported_in_the_drawing`. Fitting is width arithmetic by
  [[table-views]] round 3's design, so the tests should declare a width rather than borrow one.
  Found while hardening the message-wrap assertions in [[delay]]

