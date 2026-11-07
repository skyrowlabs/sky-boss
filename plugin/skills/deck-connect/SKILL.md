---
name: deck-connect
description: Connect this session to the other agents in its sky.boss deck — reread the deck's brief with the live roster, then introduce yourself to the primary. Use when the operator types /deck-connect, or asks whether you can see or reach the other agents in the deck.
---

# /deck-connect — join the deck's agents

You are probably one tab of a sky.boss deck: a tmux session whose tabs each run
a Claude Code agent for one repo, with a primary agent coordinating them.

1. Run `sb --json deck brief`. Its `data.brief` is the brief the deck gives
   your tab, rebuilt now with every agent currently open: who they are, their
   repos and roles, and the operator's profile instructions. Read it and follow
   it for the rest of this session. `data.peers` is the same roster as a list.
   - If it fails with "not running inside a tab", you are not in a deck. Say so
     to the operator and stop; do not message anyone.
2. Confirm the roster is live with `sb agents --scope deck` (or ListAgents). A
   peer is reached by its deck name with SendMessage.
3. Unless you are the primary, send the primary one short message: your name,
   your repo, and what you are working on now (one line). Do not ask it for
   anything yet, and do not message the other tabs unless the operator asks.
   If you are the primary, do not broadcast; just tell the operator who is in
   the deck.
4. If you have work in flight, record it with `sb deck todo add "<text>"` so it
   shows in the deck's AGENT TODOs pane. If you are waiting on the operator to rule on
   something, record it with
   `sb deck decide add "<question>" --option "<choice>" --option "<choice>"` so
   it shows in HUMAN DECISIONS. The operator rules by clicking it, and the ruling
   arrives typed into your tab. A ruling given another way, you close with
   `sb deck decide done <n> "<ruling>"`.
   Anything you need from the operator goes there, never a question in prose. A
   command only they may run is
   `sb deck decide add "<what>" --run "<command>" --until <test>`. A pull request
   you need merged is one of these, with the merge command in the row:
   `sb deck decide add "Merge <repo> PR #<n>" --run "gh pr merge <n> --repo <owner/repo> --merge --match-head-commit <sha>" --until pr:<n>@<sha>`.
   The pin makes the row read stale if the head moves.
   Something only they can do, with no command, is
   `sb deck decide add "<what>" --action`, and something merely worth knowing is
   `sb deck decide note "<text>"`. An ask written in a report or a message is not
   enough on its own: each one also goes in as a row, from the tab that acts on it.
   A command the operator must run is never left only in prose for them to copy.
5. Tell the operator, in two or three lines, who is in the deck and what you sent.
