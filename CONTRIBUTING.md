# Contributing to ibis-dune

Thanks for contributing.

## Setup

Requires **Python 3.11+** (matches `dune-client` and CI).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

For live integration tests, copy `tests/.env.example` to `tests/.env` and set `DUNE_API_KEY`.

## Test tiers

CI runs offline tests on Python **3.11, 3.12, and 3.13**. When changing dependencies or supported Python versions, verify at least one version other than your local default (e.g. via Docker `python:3.11-slim`).

- Offline (default CI gate): `pytest -m "not integration and not trino and not parity_mock" -q`
- Mocked parity replay: `pytest -m parity_mock -q`
- Integration: `pytest -m integration -q` (requires `DUNE_API_KEY`)
- Live Trino vs REST parity: `pytest -m trino -q` (requires high-tier `DUNE_API_KEY`; may consume credits)

## Fixture refresh

Refresh parity fixtures after changing parity builders or REST coercion behavior:

```bash
set -a && source tests/.env && set +a
python -m tests.capture_parity_fixtures
```

## Local quality workflow

Install hooks once:

```bash
pre-commit install
```

Run all hooks manually:

```bash
pre-commit run --all-files
```

## Boundaries

`ibis-dune` is a standalone backend package. Do not add consumer-specific coupling or application-layer behavior.

## Releases

User-facing release notes are published on [GitHub Releases](https://github.com/Firlej/ibis-dune/releases) only (no `CHANGELOG.md` in the repo).

To cut a release:

1. Add `.github/release-notes/vX.Y.Z.md` using [.github/release-template.md](.github/release-template.md) as a starting point.
2. Bump `version` in `pyproject.toml` and `__version__` in `ibis_dune/__init__.py`.
3. Merge to `main`, tag `vX.Y.Z`, and push the tag.
4. The [release workflow](.github/workflows/release.yml) runs offline tests, builds artifacts, and publishes the GitHub Release with your notes file.

## Pull request checklist

- Offline tests pass.
- `parity_mock` tests pass.
- User-visible changes include draft release notes in `.github/release-notes/vX.Y.Z.md` when preparing a version bump (published at tag time via the release workflow).
