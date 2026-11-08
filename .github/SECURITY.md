# Security

## What sky.boss is, stated plainly

**`sb run` executes commands you give it, and `sb ui` is remote code execution bound to a
port.** That is the feature, not a defect — the surface exists so a command can be launched from
a browser. It means the threat model is worth reading before you run it.

`sb` is never in the credential path. External CLIs keep their own authentication, there is no
secrets store, and nothing here reads or writes a token. That is deliberate and is what keeps the
MCP surface safe to offer to an agent.

## The surface's defences

`sb ui` is guarded by four things, none of them optional:

1. **Loopback bind.** The server never listens on a routable address.
2. **A required custom header.** This forces a CORS preflight that is never answered, and it is
   the one that actually stops a hostile page in another tab.
3. **A per-launch token**, written into the page and checked on every route.
4. **An `Origin` check.**

There is **no CORS allow-origin header anywhere**, and adding one would undo most of that. A test
asserts its absence.

What a page past that guard gets is `/api/run` with an arbitrary argv — that is, everything. The
guard is the whole defence; nothing behind it is a second line.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting** — the *Report a vulnerability* button under this
repository's **Security** tab. It opens a private thread visible only to the maintainers.

Please do not open a public issue for a security problem. A public issue is a disclosure.

Include what you would want if you were fixing it: the version (`sb --version`), the platform, the
smallest thing that reproduces it, and what you observed rather than what you concluded.

Expect a first response within a week. This is a small project and there is no on-call.

## What counts

In scope, and worth reporting:

- Anything that reaches `/api/run`, or any other route, without the guard above.
- A command's output escaping into somewhere it should not be — `sb data` is documented to carry
  parsed data only, and a probe's raw output reaching stdout would be a real bug.
- A saved tool in `tools.toml` being written or executed in a way the operator did not author.
- Anything that makes `sb` write outside `$SB_HOME` and `$SB_STATE` unasked.

Out of scope, because it is the documented design:

- `sb run` runs the argv you hand it. So does a saved tool. That is the product.
- The surface's write routes (`POST /api/tools`) are reachable by anything past the guard. This
  was argued and accepted: a page past the guard already has `/api/run` and an arbitrary argv, so
  it could append to `tools.toml` by itself. Persistence was already on that side of the boundary.
- `--env NAME=VALUE` is written verbatim into `tools.toml` and drawn in a window title. It is not
  a credential path and is documented as not being one.

## Versions

Only the latest tag is supported. This project is young and pre-1.0; there is no backport branch.
