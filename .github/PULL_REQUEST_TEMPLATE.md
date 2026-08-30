## What changed, and why

<!-- The why is the half a review needs. One paragraph. -->

## What you ran, and what it said

<!-- Not "should work" — the commands and their output. If part of this is
     unverified, say which part; that is more useful than a confident summary. -->

- [ ] `.venv/bin/python -m pytest -q`
- [ ] `npm run lint:check`
- [ ] `npm test`
- [ ] Ran it for real (which command, on what, and what came out)

## Docs

- [ ] A new round in the `docs/features/<slug>.md` that already owns this
- [ ] A new feature doc (only if nothing owns it yet)
- [ ] `docs/open.md` updated — an item leaves it by recording where it went
- [ ] N/A

## The rules this touches

<!-- Delete what does not apply. Each has a test; see CONTRIBUTING.md. -->

- [ ] Keeps `sb run` the only command that acts
- [ ] Returns a `Result` rather than printing
- [ ] No hex outside `cli/theme.py`
- [ ] Wordmark in prose, `sb` only in code spans
- [ ] No host name, home directory, or routable address added
