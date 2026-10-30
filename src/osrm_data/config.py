"""The list of countries to build, read from countries.yml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ALGORITHMS = ("ch", "mld")


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
