# osrm-data

Nightly per-country OSRM datasets (car profile) built from Geofabrik extracts and published to S3 for
osrm-server. This repository is public.

## Commands

```sh
uv sync
uv run pytest -m "not e2e"                              # e2e runs the real OSRM toolchain on Monaco
uv run --group precommit pre-commit run --all-files     # what CI runs: ruff, codespell, ty, all tests
uv run python -m osrm_data build kr --workdir /tmp/osrm # local build, uploads nothing
```

- `osrm-bindings` is pinned exactly and recorded in every manifest; `optimaru/osrm-server` must pin the same
  version. Bump it here first, let the datasets rebuild, then bump osrm-server.
- The `nightly build` workflow assumes an AWS role, so it must never run on `pull_request`.
- Country codes must match `[a-z0-9]{2,16}` (osrm-server accepts only that).

## Keeping docs in sync

- A change to the pipeline, manifest fields, published layout, CLI, workflow or countries.yml updates the
  README in the same PR (the Capacity table lists every country in countries.yml).
- Before finishing, grep the README, countries.yml comments and workflow comments for every name you touched
  and check each claim against the code.
- If the change affects what the public homepage (`optimaru/homepage`) says, note in the PR that it needs
  updating.

## Owner policies

- Everything in this public repository, including commits and PR text, is in English.
- No third-party vendor names or vendor menu terms in the product.
- Open a PR and merge it yourself after review, without asking. Deploys are the owner's.
