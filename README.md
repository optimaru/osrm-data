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
uv run python -m osrm_data build kr --workdir /tmp/osrm   # nothing leaves the machine until `publish`
uv run pytest -m "not e2e"                                # -m e2e runs the real toolchain on Monaco
```

## Add a country

Add an entry to [countries.yml](countries.yml), then start the `nightly build` workflow by hand with
that code and `upload` turned off to see whether it fits. The job summary shows the time and peak
memory of each stage.

## Capacity

Builds run on GitHub-hosted runners with 16 GB of memory and four cores, plus 16 GB of swap. Measured
with OSRM 26.10.0 and the `ch` algorithm in October 2026:

| Country | Extract | Dataset | Archive | Peak memory | Job time |
| --- | --- | --- | --- | --- | --- |
| Malaysia, Singapore and Brunei | 241 MiB | 1.4 GiB | 0.6 GiB | 6.4 GiB | 10 min |
| Taiwan | 313 MiB | 0.6 GiB | 0.3 GiB | 2.4 GiB | 13 min |
| Philippines | 584 MiB | 1.5 GiB | 0.6 GiB | 6.2 GiB | 12 min |
| South Korea | 277 MiB | 1.3 GiB | 0.6 GiB | 4.7 GiB | 17 min |
| Thailand | 314 MiB | 2.5 GiB | 1.1 GiB | 9.4 GiB | 20 min |
| Vietnam | 316 MiB | 3.1 GiB | 1.3 GiB | 12.0 GiB | 25 min |
| Australia | 927 MiB | 1.9 GiB | 0.8 GiB | 8.0 GiB | 26 min |
| Indonesia | 1660 MiB | 5.9 GiB | 2.5 GiB | 14.9 GiB | 66 min |

`extract` sets the peak. It tracks the road network rather than the extract size: Vietnam needs more
than Australia from a third of the file size. Check a new country with a test run instead of guessing.
Indonesia is at the limit of what these runners can hold, so a larger country needs a bigger machine.

## License

The code is under the [Apache License 2.0](LICENSE). The datasets are derived from OpenStreetMap
data, © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright). Anyone using them must give that
attribution.
