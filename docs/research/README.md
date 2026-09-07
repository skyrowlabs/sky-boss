# Research — ideas, and what came of looking

Documents that are **not plans**. An idea nobody has decided to look into, and the write-up of
somebody having looked, live in the same folder on purpose: splitting them would ask you to
classify at the moment you know least, and the answer would be wrong as soon as anyone did the
work. The rule is `docs/rules/docs.md` § Folder Structure; this is the folder it describes.

**Rejected ideas keep their memo rather than being deleted.** The expensive half of an
investigation is what it ruled out, and a deleted memo is an invitation to buy it twice.

## What is here

- **[ideas.md](ideas.md)** — the running list. *Should we build this at all?* Each entry is either
  live, or struck through with a pointer to where it went — a plan in `docs/TODO/`, a shipped doc
  in `docs/implementations/`, or an answer that needed no code. It moved here from `docs/ideas.md`
  on 2026-09-07; `[[ideas]]` is unchanged, which is the point of slugs.

## The three boundaries

They are easy to confuse and each one is a different question:

| Where | Question | Leaves by |
|---|---|---|
| `docs/research/` | **Should we build it at all?** | somebody deciding to, or deciding not to and keeping the memo |
| `docs/open.md` | Decided to build — **how?** | somebody deciding how, and writing the plan |
| `docs/TODO/` | Decided how — **do it** | shipping, and `dev docs file` |
| `docs/implementations/` | Shipped — **why is it like this?** | nothing; it is the record |

`docs/open.md` sits between the first and the third and is deliberately not a folder: an item
there is a paragraph nobody has yet decided is a plan, and one document per paragraph would imply
a commitment that has not been made.

The direction of travel is one-way per item, and the line that records where something went stays
behind rather than being deleted. A pointer costs one line and answers *"did we already look at
this?"* — which is the question that gets asked most and answered worst.
