# Vendored design source

`skyrow-colors_and_type.css` is Skyrow Labs' design system token file, copied unmodified from the
design-system bundle. It is here so that `cli/theme.py`'s claim to have copied it verbatim is
**checkable** rather than asserted — `tests/test_theme.py` parses this file and fails if any
token in `theme.py` has drifted from it.

That is the whole reason it is vendored. It is not a second palette and nothing imports it at
runtime; the Python constants remain the ones every consumer derives from.

**If the design system moves,** replace this file and let the test tell you which constants in
`theme.py` need updating. Do not edit `theme.py` alone — that is exactly the drift the file
exists to catch, and it is what happened once already: the palette was approximated from
jam.sense's app tokens and every hue was wrong for a week.
