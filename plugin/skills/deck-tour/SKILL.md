---
name: deck-tour
description: Show the sky.boss deck working, from the primary tab — hand up to five peers a small read-only task each, so messages, todos and two decisions move through the deck's panes while the operator watches. Use when the operator types /deck-tour, or asks to see the deck in action.
---

# /deck-tour — watch the deck's panes move

A short, harmless tour of a sky.boss deck. You hand each peer a small task.
While they work, the AGENT COMMUNICATIONS, AGENT TODOs and HUMAN DECISIONS
panes fill in, one peer asks another a question, and the operator rules on two
decisions with a click.

**Everything here is read-only.** No tab edits a file, commits, pushes or runs
anything but `git` reads and `sb deck`. That is what makes the tour safe to run
in a real deck, beside real work.

Keep every message and every row to one short line: the panes are the show.

## If you are the primary

1. Run `sb --json deck brief`. You are the primary when `data.agent` equals
   `data.primary`; if not, say that `/deck-tour` runs from the primary tab and
   stop. If it fails with "not running inside a tab", say you are not in a deck
   and stop.
2. Take up to five peers from `data.peers`, in roster order, that are live in
   `sb agents --scope deck`. With fewer than two live, say so and stop. Give
   them the tasks below in order: the first peer gets task 1, the second task 2,
   and so on. With fewer than five, skip task 3 when there are fewer than four
   peers, since its partner is the peer with task 4.
3. For each peer, add one todo of your own:
   `sb deck todo add "Tour: hear back from <peer>"`.
4. Send each peer one SendMessage starting with `deck-tour:`, naming its task
   by number and, for task 3, its partner. Send them one after another.
5. End your turn. Replies arrive in your tab as messages. As each one arrives,
   mark that peer's todo done (`sb deck todo done <n>`, the number
   `sb deck todo list` gives it). When every peer has reported, post the close:
   `sb deck decide note "Tour done: every peer reported back"`.
6. Tell the operator in a few lines what each peer said. Then add that `M-x`
   (`sb deck clear`) clears the tour's ticked rows.

## The tasks

1. Report the branch and its last commit subject.
2. Count the files the repo tracks, and ask the operator whether to report it
   as a number or a sentence.
3. Ask the peer with task 4 what its repo's last commit subject is, then report
   that answer to the primary.
4. Report how many commits the branch has. If the peer with task 3 asks you
   something, answer it in one line first.
5. Report the date of the last commit, and ask the operator whether to report
   it as a date or as an age.

## If you are a peer, and a `deck-tour:` message arrives

Do exactly what your task asks, in this order, and nothing else:

1. `sb deck todo add "<your task, in a few words>"`.
2. Do the read-only part with `git`: `git branch --show-current`,
   `git log -1 --format=%s`, `git ls-files | wc -l`, `git rev-list --count HEAD`,
   or `git log -1 --format=%cs`. For task 3, SendMessage the partner peer
   instead, add a second todo `sb deck todo add "Wait for <partner>"`, and end
   your turn until it answers.
3. **If your task asks the operator**, run one of these commands exactly as
   written, then end your turn and wait:
   `sb deck decide add "Report the file count as?" --option "A number" --option "A sentence"`
   or
   `sb deck decide add "Report the last commit as?" --option "A date" --option "An age"`.
   The ruling arrives typed into your tab. Never answer it yourself.
4. Send the primary one SendMessage with the result. If you asked the operator,
   give it in the form they chose and say which form that was.
5. Mark each of your todos done: `sb deck todo done <n>`.

If a peer messages you mid-tour with a question, answer it in one line by
SendMessage, then carry on with your own task.
