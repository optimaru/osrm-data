# osrm-data

Nightly per-country [OSRM](https://project-osrm.org) road network datasets for the car profile,
built from [OpenStreetMap](https://www.openstreetmap.org) extracts.

Every night a GitHub Actions job checks each country in [countries.yml](countries.yml). If its extract
changed, or the OSRM version did, the job rebuilds the dataset and publishes it to S3. Unchanged
countries are skipped.

## Published layout

```
<code>/latest.json                 manifest, written last
<code>/<version>/<code>.tar.zst    immutable dataset, the last three are kept
```

Versions are UTC build timestamps. `latest.json` records the archive's key, SHA-256 and sizes, the OSRM
version, the algorithm and the time and peak memory of each stage. A reader must use the same
`osrm-bindings` version as `osrm_version`, because the data format changes between releases.

Files only the preprocessing tools read are left out of the archive, which makes it about a quarter
smaller.

## Build locally

```sh
uv sync
uv run python -m osrm_data build kr --workdir /tmp/osrm   # nothing leaves the machine without --bucket
uv run pytest -m "not e2e"                                # -m e2e runs the real toolchain on Monaco
```

## Add a country

Add an entry to [countries.yml](countries.yml), then start the `nightly build` workflow by hand with
that code and `upload` turned off to see whether it fits. The job summary shows the time and peak
memory of each stage.

## Capacity

<!-- capacity -->

## License

The code is under the [Apache License 2.0](LICENSE). The datasets are derived from OpenStreetMap
data, © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright). Anyone using them must give that
attribution.
