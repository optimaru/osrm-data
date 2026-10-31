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

A code is 2 to 16 lowercase letters or digits, because osrm-server accepts only that. Use the ISO country
code, then the subdivision for a region (`usca`, `deby`), or a word where the subdivision has no code
(`usnortheast`, `insouth`). The dataset also has to be smaller than the memory budget of the osrm-server
that serves it.

## Capacity

Builds run on GitHub-hosted runners with 16 GB of memory and four cores, plus 16 GB of swap. Measured
with OSRM 26.10.0 and the `ch` algorithm in October 2026:

| Country | Extract | Dataset | Archive | Peak memory | Job time |
| --- | --- | --- | --- | --- | --- |
| Mongolia | 59 MiB | 0.1 GiB | 0.1 GiB | 0.7 GiB | 1 min |
| Laos | 51 MiB | 0.2 GiB | 0.1 GiB | 1.1 GiB | 1 min |
| Hawaii | 26 MiB | 0.1 GiB | 0.0 GiB | 0.4 GiB | 1 min |
| Slovakia | 331 MiB | 0.3 GiB | 0.1 GiB | 1.7 GiB | 2 min |
| Cambodia | 39 MiB | 0.3 GiB | 0.1 GiB | 1.0 GiB | 3 min |
| New Zealand | 386 MiB | 0.5 GiB | 0.2 GiB | 2.5 GiB | 4 min |
| Germany, Hesse | 331 MiB | 0.3 GiB | 0.2 GiB | 1.8 GiB | 4 min |
| Nevada | 118 MiB | 0.3 GiB | 0.1 GiB | 1.3 GiB | 4 min |
| Romania | 317 MiB | 0.7 GiB | 0.3 GiB | 3.2 GiB | 6 min |
| Kentucky | 147 MiB | 0.8 GiB | 0.3 GiB | 3.3 GiB | 6 min |
| Uzbekistan | 119 MiB | 0.6 GiB | 0.3 GiB | 2.2 GiB | 7 min |
| Bangladesh | 339 MiB | 0.7 GiB | 0.3 GiB | 2.8 GiB | 7 min |
| Hungary | 312 MiB | 0.4 GiB | 0.2 GiB | 1.9 GiB | 7 min |
| British Columbia | 1190 MiB | 0.4 GiB | 0.2 GiB | 6.1 GiB | 7 min |
| Alabama | 144 MiB | 0.8 GiB | 0.3 GiB | 3.0 GiB | 7 min |
| Alberta | 335 MiB | 0.4 GiB | 0.2 GiB | 1.9 GiB | 8 min |
| South Carolina | 157 MiB | 0.7 GiB | 0.3 GiB | 3.0 GiB | 8 min |
| Maryland | 206 MiB | 0.6 GiB | 0.3 GiB | 2.8 GiB | 8 min |
| Germany, Baden-Wuerttemberg | 621 MiB | 0.7 GiB | 0.3 GiB | 3.4 GiB | 9 min |
| Chile | 334 MiB | 0.9 GiB | 0.4 GiB | 3.9 GiB | 9 min |
| Malaysia, Singapore and Brunei | 241 MiB | 1.4 GiB | 0.6 GiB | 6.4 GiB | 10 min |
| Kazakhstan | 214 MiB | 0.6 GiB | 0.3 GiB | 2.2 GiB | 10 min |
| Czech Republic | 907 MiB | 0.7 GiB | 0.3 GiB | 4.0 GiB | 11 min |
| Tennessee | 182 MiB | 1.0 GiB | 0.4 GiB | 3.9 GiB | 11 min |
| Virginia | 409 MiB | 1.4 GiB | 0.6 GiB | 5.9 GiB | 11 min |
| Philippines | 584 MiB | 1.5 GiB | 0.6 GiB | 6.2 GiB | 12 min |
| Germany, Bavaria | 816 MiB | 1.1 GiB | 0.5 GiB | 5.0 GiB | 12 min |
| Arizona | 290 MiB | 0.8 GiB | 0.3 GiB | 3.2 GiB | 12 min |
| Taiwan | 313 MiB | 0.6 GiB | 0.3 GiB | 2.4 GiB | 13 min |
| Quebec | 1106 MiB | 0.6 GiB | 0.3 GiB | 6.1 GiB | 13 min |
| Germany, North Rhine-Westphalia | 873 MiB | 0.9 GiB | 0.5 GiB | 4.3 GiB | 14 min |
| Georgia | 341 MiB | 1.3 GiB | 0.6 GiB | 5.2 GiB | 14 min |
| North Carolina | 410 MiB | 1.7 GiB | 0.8 GiB | 6.9 GiB | 15 min |
| Washington | 348 MiB | 1.0 GiB | 0.4 GiB | 4.1 GiB | 15 min |
| Gulf Cooperation Council | 244 MiB | 1.7 GiB | 0.7 GiB | 6.2 GiB | 16 min |
| Netherlands | 1343 MiB | 0.9 GiB | 0.4 GiB | 6.4 GiB | 16 min |
| South Korea | 277 MiB | 1.3 GiB | 0.6 GiB | 4.7 GiB | 17 min |
| Ontario | 978 MiB | 0.8 GiB | 0.4 GiB | 6.2 GiB | 17 min |
| India, western zone | 211 MiB | 1.8 GiB | 0.8 GiB | 6.7 GiB | 18 min |
| Thailand | 314 MiB | 2.5 GiB | 1.1 GiB | 9.4 GiB | 20 min |
| India, eastern zone | 236 MiB | 2.3 GiB | 0.9 GiB | 8.3 GiB | 21 min |
| Poland | 2016 MiB | 2.4 GiB | 1.1 GiB | 10.2 GiB | 22 min |
| Indiana | 191 MiB | 1.0 GiB | 0.5 GiB | 4.0 GiB | 24 min |
| Vietnam | 316 MiB | 3.1 GiB | 1.3 GiB | 12.0 GiB | 25 min |
| Ohio | 311 MiB | 1.6 GiB | 0.7 GiB | 6.2 GiB | 25 min |
| Australia | 927 MiB | 1.9 GiB | 0.8 GiB | 8.0 GiB | 26 min |
| Brazil, South | 409 MiB | 1.7 GiB | 0.7 GiB | 6.4 GiB | 26 min |
| Michigan | 301 MiB | 1.3 GiB | 0.6 GiB | 5.3 GiB | 26 min |
| Florida | 629 MiB | 1.8 GiB | 0.8 GiB | 7.3 GiB | 29 min |
| Illinois | 345 MiB | 1.3 GiB | 0.6 GiB | 4.9 GiB | 29 min |
| India, central zone | 335 MiB | 2.9 GiB | 1.2 GiB | 10.4 GiB | 32 min |
| Spain | 1427 MiB | 2.5 GiB | 1.1 GiB | 10.9 GiB | 33 min |
| Egypt | 170 MiB | 1.7 GiB | 0.8 GiB | 5.9 GiB | 35 min |
| India, northern zone | 214 MiB | 2.4 GiB | 1.0 GiB | 8.7 GiB | 39 min |
| Turkey | 621 MiB | 2.8 GiB | 1.2 GiB | 9.9 GiB | 40 min |
| Great Britain | 2092 MiB | 3.6 GiB | 1.7 GiB | 14.7 GiB | 40 min |
| California | 1272 MiB | 2.8 GiB | 1.3 GiB | 11.3 GiB | 49 min |
| Brazil, Southeast | 822 MiB | 3.5 GiB | 1.5 GiB | 13.5 GiB | 51 min |
| Texas | 692 MiB | 3.3 GiB | 1.5 GiB | 12.7 GiB | 53 min |
| India, southern zone | 533 MiB | 4.0 GiB | 1.7 GiB | 14.3 GiB | 56 min |
| France | 4870 MiB | 6.4 GiB | 2.9 GiB | 15.0 GiB | 81 min |
| Indonesia | 1660 MiB | 5.9 GiB | 2.5 GiB | 15.0 GiB | 83 min |
| United States, Northeast | 1724 MiB | 5.3 GiB | 2.4 GiB | 14.7 GiB | 91 min |
| Mexico | 617 MiB | 5.0 GiB | 2.2 GiB | 14.7 GiB | 114 min |
| Japan | 2446 MiB | 7.6 GiB | 3.4 GiB | 14.9 GiB | 258 min |

`extract` sets the peak. It tracks the road network rather than the extract size: Vietnam needs more
than Australia from a third of the file size. Check a new country with a test run instead of guessing.
Indonesia, Japan, France, Great Britain, Mexico and the US Northeast are at the limit of what these
runners can hold: all reach about 15 GiB in `extract`, and Japan's `contract` takes over two and a half
hours, which leaves about 90 minutes of the job's 350 minute timeout. If one of them outgrows the runner
its job fails and readers keep the last version.

The whole of India and Brazil and the US Midwest and South lost their runner, which is how running out of
memory shows up. The US West built in 187 minutes, but its 8.01 GiB dataset is over osrm-server's default
`OSRM_MAX_LOADED_GB` of 8, so it could not be served. These are built as smaller Geofabrik regions instead.

A region is its own dataset, so **a route cannot cross its border**, and a reader has to pick the code for
the coordinates it has. Prefer the largest region that fits, so that a metropolitan area stays in one
dataset: that is why the US Northeast is whole. Washington D.C. is the known gap, split between Virginia
and Maryland, with the district itself not built.

Geofabrik publishes no `.md5` for the whole of Germany and sends its extract to a mirror, so Germany is built
by state.

## License

The code is under the [Apache License 2.0](LICENSE). The datasets are derived from OpenStreetMap
data, © OpenStreetMap contributors, available under the
[Open Database License](https://www.openstreetmap.org/copyright). Anyone using them must give that
attribution.
