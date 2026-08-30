# Sample data for the README's screenshots

Invented. It exists so `render-canvas.mjs` and `render-mark.py` photograph the
same thing, rather than each inventing its own five rows and drifting.

**Both scripts copy this into a neutral temporary directory before running.**
They never point sky.boss at these files in place, because the path is drawn in
a window title and in a `follow` band — and the path to a checkout names
whoever's home it sits in. That is the same rule `tests/test_publication.py`
enforces on the tree, arriving somewhere a test cannot look: inside a PNG.

`agent.log`'s lines are chosen to land on the built-in highlight rules — a
leading timestamp, the job tag after it, a path, a number with its unit, verdict
glyphs, a status light, a quoted string, a parenthesised host, a URL and an
issue reference. See `BUILTINS` in `cli/highlight.py`. If a rule is added there,
add a line here that shows it.

Nothing here names a real host or a routable address: `host-2` is the
placeholder the highlight legend uses, and `192.0.2.10` is RFC 5737
documentation space.
