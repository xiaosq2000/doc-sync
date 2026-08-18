# Contributing

Thank you for helping improve doc-sync. Bug reports should include the command,
configuration, Git state, expected result, and actual result. Remove private
paths or repository contents before posting logs.

## Development setup

Doc-sync requires Python 3.11 or newer and has no runtime dependencies. In a
standalone checkout:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --editable .
python -m pip install ruff ty
```

Run the checks before opening a pull request:

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
ty check
```

Changes to configuration behavior, JSON output, exit codes, or agent adapters
must include contract tests and corresponding README updates. Keep the core
`evaluate()` function independent of Git, file I/O, session state, and agent
protocols.
