"""Turns one OpenStreetMap extract into a packaged OSRM dataset."""

import hashlib
import io
import os
import resource
import subprocess
import sys
import tarfile
import time
import urllib.request
from collections.abc import Callable
from compression import zstd
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import osrm

from osrm_data.config import DATA_ATTRIBUTION, DATA_LICENSE, DATA_LICENSE_URL, Country

OSRM_VERSION = metadata.version("osrm-bindings")
PROFILE = Path(osrm.__file__).parent / "share" / "profiles" / "car.lua"

# Written by the preprocessing tools but never read when serving. Leaving them out
# makes a dataset about a quarter smaller.
BUILD_ONLY_SUFFIXES = frozenset({".ebg", ".cnbg", ".cnbg_to_ebg", ".enw", ".turn_penalties_index"})

# Travels inside every archive, so a copy of the dataset keeps its license and credit.
NOTICE_FILE = "NOTICE.txt"


# Waits between attempts to reach the extract server. It answers with 5xx, resets
# and timeouts for a while at a time, and one failed request used to cost a country
# its night.
RETRY_DELAYS = (30, 60, 120, 240)


@dataclass(frozen=True)
class Extract:
    """One published extract: a file that never changes, and its checksum."""

    url: str
    md5: str


def notice(country: Country, extract: Extract) -> str:
    return (
        f"OSRM road network dataset for {country.name}, car profile.\n"
        "\n"
        f"Derived from OpenStreetMap data, {DATA_ATTRIBUTION}\n"
        "(https://www.openstreetmap.org/copyright), and made available under the\n"
        f"Open Database License ({DATA_LICENSE}): {DATA_LICENSE_URL}\n"
        "Any use must keep this notice and give that attribution.\n"
        "\n"
        f"Source extract: {extract.url} (MD5 {extract.md5})\n"
        f"Built with OSRM {OSRM_VERSION} ({country.algorithm}) by https://github.com/optimaru/osrm-data\n"
    )


@dataclass
class Build:
    archive: Path
    dataset_bytes: int
    stages: dict[str, dict[str, float]] = field(default_factory=dict)


class ChecksumMismatch(RuntimeError):
    pass


def _retrying[T](what: str, attempt: Callable[[], T]) -> T:
    for delay in RETRY_DELAYS:
        try:
            return attempt()
        # URLError, HTTPError and timeouts are all OSErrors.
        except (OSError, ChecksumMismatch) as error:
            print(f"{what}: {error!r}, retrying in {delay}s", file=sys.stderr, flush=True)
            time.sleep(delay)
    return attempt()


def resolve(url: str) -> Extract:
    """Pins the extract a `-latest` URL points to now.

    The server answers `-latest` with a redirect to a dated file, and a pool of caching
    proxies serves both. While a new extract is being published, `-latest.md5` and
    `-latest` can come from different days, which showed up as 404s and checksum
    mismatches. A dated file and its `.md5` never change, so reading the checksum and
    later the file by that name always gives a matching pair.
    """

    def attempt() -> Extract:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as response:
            pinned = response.url
        with urllib.request.urlopen(f"{pinned}.md5", timeout=60) as response:
            return Extract(url=pinned, md5=response.read().decode().split()[0])

    return _retrying(url, attempt)


def download(extract: Extract, target: Path) -> None:
    def attempt() -> None:
        digest = hashlib.md5(usedforsecurity=False)
        with urllib.request.urlopen(extract.url, timeout=60) as response, target.open("wb") as out:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != extract.md5:
            raise ChecksumMismatch(f"{extract.url}: checksum mismatch")

    _retrying(extract.url, attempt)


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


def package(base: Path, archive: Path, threads: int, notice_text: str) -> int:
    """Packs the files needed for serving, with the notice, and returns the dataset's uncompressed size."""
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
        body = notice_text.encode()
        info = tarfile.TarInfo(NOTICE_FILE)
        info.size = len(body)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(body))
    return size


def build(country: Country, extract: Extract, workdir: Path) -> Build:
    workdir.mkdir(parents=True, exist_ok=True)
    threads = os.cpu_count() or 1
    pbf = workdir / f"{country.code}.osm.pbf"
    download(extract, pbf)
    base, stages = build_dataset(country, pbf, threads)
    archive = workdir / f"{country.code}.tar.zst"
    size = package(base, archive, threads, notice(country, extract))
    return Build(archive=archive, dataset_bytes=size, stages=stages)
