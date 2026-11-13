---
name: deck-tour
description: Show the sky.boss deck working, from the primary tab — hand two peers a small read-only task each, so messages, todos and one decision move through the deck's panes while the operator watches. Use when the operator types /deck-tour, or asks to see the deck in action.
---

# /deck-tour — watch the deck's panes move

A short, harmless tour of a sky.boss deck. You hand two peers a small task
each. While they work, the AGENT COMMUNICATIONS, AGENT TODOs and HUMAN
DECISIONS panes fill in, and the operator rules on one decision with a click.

**Everything here is read-only.** No tab edits a file, commits, pushes or runs
anything but `git` reads and `sb deck`. That is what makes the tour safe to run
in a real deck, beside real work.

Keep every message and every row to one short line: the panes are the show.

## If you are the primary

1. Run `sb --json deck brief`. You are the primary when `data.agent` equals
   `data.primary`; if not, say that `/deck-tour` runs from the primary tab and
   stop. If it fails with "not running inside a tab", say you are not in a deck
   and stop.
2. Take the first two peers in `data.peers` that are live in
   `sb agents --scope deck`. Call them A and B. With fewer than two live, say so
   and stop.
3. Add your own todo: `sb deck todo add "Tour: hear back from A and B"`, with
   their names.
4. Send A one SendMessage, starting with `deck-tour:` so it knows what this is:
   *deck-tour: as A, add a todo, report your branch and its last commit subject
   back to me in one line, then mark the todo done.*
5. Send B one SendMessage, the same way:
   *deck-tour: as B, add a todo, count the files your repo tracks, raise a
   decision asking the operator whether to report it as a number or a sentence,
   wait for the ruling, report in the form chosen, then mark the todo done.*
6. End your turn. The replies arrive in your tab as messages. When both are in,
   mark your todo done (`sb deck todo done <n>`, using the number `sb deck todo
   list` gives it), then post the close:
   `sb deck decide note "Tour done: A and B reported back"`.
7. Tell the operator in two lines what each peer said. Then add that `M-x`
   (`sb deck clear`) clears the tour's ticked rows.

## If you are a peer, and a `deck-tour:` message arrives

Do exactly what it asks, in this order, and nothing else:

1. `sb deck todo add "<the task, in a few words>"`.
2. Do the read-only part: `git branch --show-current` and
   `git log -1 --format=%s`, or `git ls-files | wc -l`.
3. **If you were asked for a decision**, run this command exactly as written,
   then end your turn and wait:
   `sb deck decide add "Report the file count as?" --option "A number" --option "A sentence"`.
   The ruling arrives typed into your tab. Never answer it yourself.
4. Send the primary one SendMessage with the result, in the chosen form if you
   asked for one.
5. Mark your todo done: `sb deck todo done <n>`.
