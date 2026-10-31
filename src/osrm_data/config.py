"""The list of countries to build, read from countries.yml."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ALGORITHMS = ("ch", "mld")
# osrm-server puts a code in URLs and S3 keys and accepts only this shape.
CODE = re.compile(r"[a-z0-9]{2,16}")


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    url: str
    algorithm: str


def load_countries(path: Path) -> dict[str, Country]:
    raw = yaml.safe_load(path.read_text())
    source = raw["source"].rstrip("/")
    countries: dict[str, Country] = {}
    for entry in raw["countries"]:
        code = entry["code"]
        if not CODE.fullmatch(code):
            raise ValueError(f"{code!r}: a code is 2 to 16 lowercase letters or digits")
        algorithm = entry.get("algorithm", raw["algorithm"])
        if algorithm not in ALGORITHMS:
            raise ValueError(f"{code}: unknown algorithm {algorithm!r}")
        if code in countries:
            raise ValueError(f"{code}: listed twice")
        countries[code] = Country(
            code=code,
            name=entry["name"],
            url=f"{source}/{entry['extract']}-latest.osm.pbf",
            algorithm=algorithm,
        )
    return countries
