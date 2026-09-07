# Contributing to socialdl

Thanks for your interest in improving socialdl! This is a small, focused tool —
contributions that keep it simple and well-tested are very welcome.

## Development setup

```bash
git clone https://github.com/StaticB1/socialdl
cd socialdl
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Running the tests

```bash
.venv/bin/pytest
```

The test suite is offline — it exercises the pure functions (URL/platform
detection, filter building, output parsing) and never touches the network.
Please add tests for any logic you change.

## Project layout

```
socialdl/
├── core.py         # UI-agnostic download/probe logic + data types
├── config.py       # config file + env var resolution
├── cli.py          # command-line interface (entry point: socialdl)
├── mcp_server.py   # MCP server (entry point: socialdl-mcp)
└── http_server.py  # FastAPI HTTP API (entry point: socialdl-serve)
```

All three interfaces are thin adapters over `core.download()` / `core.probe()`.
New capabilities generally belong in `core.py` (as a `DownloadOptions` field) and
are then exposed in each interface.

## Guidelines

- Keep the core UI-agnostic: no printing or `sys.exit` in `core.py` — return a
  `DownloadResult`.
- Match the existing style; keep functions small and comments purposeful.
- If you add a flag, wire it through CLI, MCP, and HTTP, and document it in the
  README options table.
- Be honest about platform limitations in help text and docs (see the date/video
  caveats) rather than papering over them.

## Reporting bugs

Open an issue with the exact command, the platform, and the (redacted) output.
Never paste cookies, tokens, or other credentials into an issue.
