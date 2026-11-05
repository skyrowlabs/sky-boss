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
   shows in the deck's TODOS pane. If you are waiting on the operator to rule on
   something, record it with `sb deck decide add "<question>"` so it shows in
   DECISIONS, and close it with `sb deck decide done <n> "<ruling>"` once ruled.
5. Tell the operator, in two or three lines, who is in the deck and what you sent.
