# Ideas List

*Note: This is a list of potential ideas to add. Remove them if once spec'd or shelved*

*This file answers **should we build it**. Questions about something already being
built — decided, but not decided how — live in `docs/open.md`.*

- ~~watcher for cron jobs~~ — spec'd as [[file-follow]] round 2 (`sb follow --due 15m <path>`);
  the systemd half needs no code, see the doc
- ~~piping commands to claude or other agents~~ — answered: chaining needs nothing (`sb follow
  -- claude -p …` already works, and a pipeline is a shell pipe). The inverse is spec'd as
  [[mcp]] — the tools offered to an agent over stdio
- ~~future runs (non crontab or systemd), sb run --delay=[seconds] [cmd]~~ — spec'd as [[delay]]
- ~~build in embedded scrolling for follow~~ — shipped as [[follow]] round 3. The inherited
  rejection relied on "scrollback and `less` already exist", which is false for a follow: a line
  pushed out of the visible frame was never printed anywhere
- an opt-in `--pty` for follow — **re-measured 2026-08-23 and the case is now half of what it
  was.** The buffering half is already fixed: `child_env(stream=True)` sets `PYTHONUNBUFFERED=1`
  ([[subprocess-env]] round 3), so a Python child streams line by line under sb where a raw pipe
  holds everything to exit. For a *non*-Python tool `stdbuf -oL` works — measured on a C binary,
  2.00s-all-at-once becomes 0.4s apart — and it needs no sb feature at all, because
  `sb follow -- stdbuf -oL <cmd>` is an argv the operator can type and save. What is left is only a
  tool's **auto** colour (`git log --oneline` emits 0 escapes to a pipe, 80 with colour forced),
  bought at the cost of control sequences in the ring, resize handling, and the child believing it
  is interactive — which means pagers and progress bars. Weaker than it looked; shelve unless the
  colour alone is worth it
- ~~a log analyzer / view setup utility~~ — answered: lnav 0.14.0 headless already emits JSON
  (`lnav -n -q -c ';SELECT …' -c ':write-json-to -'`), so it is a `sb data --from json --` source
  and a saved tool, not a new command. Measured 2026-08-23
- ~~a richer result header (type, dimensions, size, modified, END OF DATA)~~ — split by owner:
  type and dimensions are in-band, spec'd as [[table-views]] round 4; the band and the terminator
  are out-of-band, spec'd as [[chrome]] round 3. `size`/`modified` were already on chrome's file
  cursor row. The leading `|` gutter is rejected — it breaks copy-paste and `sb read` is verbatim
  by contract
- ~~a centralized system to manage how six projects' agents work~~ — spec'd as [[roll-call]]
- ~~`--cols` naming a column that does not exist renders dashes rather than saying so~~ — fixed as
  [[table-views]] round 5; still drawn, now reported, in both renderers
- ~~two table tests inherit the ambient terminal width instead of pinning one~~ — fixed as
  [[table-views]] round 5. The suite is now clean from 40 to 300 columns; it had passed only at 80
  since it was written

