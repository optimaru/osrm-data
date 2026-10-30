"""Turns one OpenStreetMap extract into a packaged OSRM dataset."""

import hashlib
import os
import resource
import subprocess
import sys
import tarfile
import time
import urllib.request
from compression import zstd
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import osrm

from osrm_data.config import Country

OSRM_VERSION = metadata.version("osrm-bindings")
PROFILE = Path(osrm.__file__).parent / "share" / "profiles" / "car.lua"

# Written by the preprocessing tools but never read when serving. Leaving them out
# makes a dataset about a quarter smaller.
BUILD_ONLY_SUFFIXES = frozenset({".ebg", ".cnbg", ".cnbg_to_ebg", ".enw", ".turn_penalties_index"})


@dataclass
class Build:
    archive: Path
    dataset_bytes: int
    stages: dict[str, dict[str, float]] = field(default_factory=dict)


def fetch_md5(url: str) -> str:
    """Reads the published checksum, which is cheap enough to compare every night."""
    with urllib.request.urlopen(f"{url}.md5", timeout=60) as response:
        return response.read().decode().split()[0]


def download(url: str, target: Path, expected_md5: str) -> None:
    digest = hashlib.md5(usedforsecurity=False)
    with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as out:
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != expected_md5:
        raise RuntimeError(f"{url}: checksum mismatch")


def _peak_child_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is in bytes on macOS and in KiB on Linux.
    return peak / 2**20 if sys.platform == "darwin" else peak / 2**10


def _run_stage(name: str, *args: str | Path | int, stages: dict[str, dict[str, float]]) -> None:
    started = time.monotonic()
    subprocess.run([sys.executable, "-m", "osrm", name, *map(str, args)], check=True)
    stages[name] = {
        "seconds": round(time.monotonic() - started, 1),
        # A high-water mark across stages: it never falls, so it shows which stage set the peak.
        "peak_rss_mib": round(_peak_child_rss_mib()),
    }


def build_dataset(country: Country, pbf: Path, threads: int) -> tuple[Path, dict[str, dict[str, float]]]:
    """Runs the OSRM toolchain and returns the dataset base path and per-stage measurements."""
    stages: dict[str, dict[str, float]] = {}
    workdir = pbf.parent
    _run_stage("extract", "-p", PROFILE, "-t", threads, pbf, stages=stages)
    pbf.unlink()

    base = workdir / f"{country.code}.osrm"
    if country.algorithm == "ch":
        _run_stage("contract", "-t", threads, base, stages=stages)
    else:
        _run_stage("partition", "-t", threads, base, stages=stages)
        _run_stage("customize", "-t", threads, base, stages=stages)
    return base, stages


def package(base: Path, archive: Path, threads: int) -> int:
    """Packs the files needed for serving and returns their uncompressed size."""
    size = 0
    options: dict[int, int] = {
        zstd.CompressionParameter.compression_level: 3,
        zstd.CompressionParameter.nb_workers: threads,
    }
    with tarfile.open(archive, "w:zst", options=options) as tar:
        for path in sorted(base.parent.glob(f"{base.name}.*")):
            if path.name[len(base.name) :] in BUILD_ONLY_SUFFIXES:
                continue
            size += path.stat().st_size
            tar.add(path, arcname=path.name)
    return size


def build(country: Country, md5: str, workdir: Path) -> Build:
    workdir.mkdir(parents=True, exist_ok=True)
    threads = os.cpu_count() or 1
    pbf = workdir / f"{country.code}.osm.pbf"
    download(country.url, pbf, md5)
    base, stages = build_dataset(country, pbf, threads)
    archive = workdir / f"{country.code}.tar.zst"
    return Build(archive=archive, dataset_bytes=package(base, archive, threads), stages=stages)
