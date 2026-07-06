# Upstream merge notes

This package is structured so a future contribution to [ibis-project/ibis](https://github.com/ibis-project/ibis) is mostly a copy/move into `ibis/backends/dune/` rather than a rewrite.

## Current install

```bash
pip install ibis-dune
```

`pip install 'ibis-framework[dune]'` is **not** available until ibis-framework defines a `dune` optional extra upstream.

## Entry point

Registered under the standard `ibis.backends` group:

```toml
[project.entry-points."ibis.backends"]
dune = "ibis_dune"
```

After install: `import ibis; con = ibis.dune.connect(dune_api_key="...")`.

`0.1.0` is the first public PyPI release of this standalone package.

## Implemented in this repo (v0.1.0 scope)

- Backend composition and connection via `do_connect(...)`
- Trino-first execution with automatic REST fallback
- Trino/REST parity handling for `execute`, `_cursor_batches`, schema inference, and key coercions
- `DuneCompiler` / `DuneType` with `uint256` mapping
- SQL helper ops: `hex_literal`, `raw_predicate`, `raw_scalar`
- Backend-specific exceptions: `DuneQueryError`, `DuneResultTooLargeError`
- `ibis.backends` entry point registration (`dune = "ibis_dune"`)
- Typed package marker (`py.typed`)
- Contributor workflow docs (`CONTRIBUTING.md`)
- Quality tooling (`ruff`, `pre-commit`) and CI jobs:
  - offline pytest matrix
  - parity mock replay tests
  - package build + `twine check`
  - pre-commit hooks verification

## Upstream PR checklist

- [ ] `Backend` in `ibis/backends/dune/__init__.py` with `do_connect(dune_api_key=...)`
- [ ] Optional `_from_url` for `dune://` URLs
- [ ] `DuneCompiler` / `DuneType` (sqlglot `Dune` dialect, `uint256` type mapping)
- [ ] Trino + REST execution fallback, schema fetch, cursor cleanup
- [ ] Tests under ibis backend conventions
- [ ] Docs page at `ibis-project.org/backends/dune/`
- [ ] Optional extra in ibis `pyproject.toml`: `dune = [...]`
- [ ] Apache-2.0 license alignment

## Future / out of scope for this package now

- hatchling + dynamic versioning
- mypy
- scheduled integration CI with `DUNE_API_KEY` secrets
- mkdocs/docs site expansion

## Publishing workflow notes (deferred)

PyPI publishing workflow automation (Trusted Publishing / OIDC) is intentionally deferred.
Current release validation is:

```bash
python -m build
twine check dist/*
```

Trusted Publishing can be added later once release cadence stabilizes.
