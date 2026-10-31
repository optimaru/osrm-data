"""Command line entry point used by the nightly workflow.

python -m osrm_data matrix                    print the countries as a JSON array
python -m osrm_data matrix --only "kr jp"     the same for a subset, rejecting unknown codes
python -m osrm_data build kr --bucket NAME    build kr in the workdir if its extract changed
python -m osrm_data build kr                  build without touching S3
python -m osrm_data publish kr --bucket NAME  upload what build left in the workdir
"""

import argparse
import json
import os
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from osrm_data.config import Country, load_countries
from osrm_data.pipeline import OSRM_VERSION, build, fetch_md5
from osrm_data.store import Manifest, Store, manifest_for

COUNTRIES_FILE = Path(__file__).parents[2] / "countries.yml"
MANIFEST_FILE = "manifest.json"


def is_current(manifest: Manifest | None, country: Country, md5: str) -> bool:
    return (
        manifest is not None
        and manifest.source_md5 == md5
        and manifest.algorithm == country.algorithm
        and manifest.osrm_version == OSRM_VERSION
    )


def summarize(country: Country, status: str, stages: dict[str, dict[str, float]] | None = None) -> None:
    lines = [f"### {country.name} ({country.code}): {status}", ""]
    if stages:
        lines += ["| stage | seconds | peak RSS so far (MiB) |", "| --- | --- | --- |"]
        lines += [f"| {name} | {s['seconds']} | {s['peak_rss_mib']} |" for name, s in stages.items()]
    text = "\n".join(lines) + "\n"
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as file:
            file.write(text)


def run_build(country: Country, bucket: str | None, workdir: Path, force: bool) -> str:
    target = workdir / country.code
    shutil.rmtree(target, ignore_errors=True)
    md5 = fetch_md5(country.url)
    if bucket and not force and is_current(Store(bucket).latest(country.code), country, md5):
        summarize(country, "unchanged, skipped")
        return "skipped"

    result = build(country, md5, target)
    now = datetime.now(UTC)
    manifest = manifest_for(
        code=country.code,
        version=now.strftime("%Y%m%dT%H%M%SZ"),
        algorithm=country.algorithm,
        osrm_version=OSRM_VERSION,
        archive=result.archive,
        dataset_bytes=result.dataset_bytes,
        source_url=country.url,
        source_md5=md5,
        built_at=now.isoformat(),
        stages=result.stages,
    )
    text = json.dumps(asdict(manifest), indent=2)
    print(text)
    (target / MANIFEST_FILE).write_text(text)
    summarize(country, "built", result.stages)
    return "built"


def run_publish(country: Country, bucket: str, workdir: Path) -> str:
    """Uploads what build left behind.

    A separate command so the job can take new credentials first: they last an
    hour, and a large country takes longer than that to build.
    """
    target = workdir / country.code
    manifest_file = target / MANIFEST_FILE
    if not manifest_file.exists():
        return "skipped"
    manifest = Manifest(**json.loads(manifest_file.read_text()))
    Store(bucket).publish(target / f"{country.code}.tar.zst", manifest)
    summarize(country, "published")
    return "published"


def main() -> None:
    parser = argparse.ArgumentParser(prog="osrm_data")
    commands = parser.add_subparsers(dest="command", required=True)
    matrix_command = commands.add_parser("matrix")
    matrix_command.add_argument("--only", default="", help="space-separated country codes")
    build_command = commands.add_parser("build")
    build_command.add_argument("code")
    build_command.add_argument("--bucket", help="skip the build if this bucket holds the current extract")
    build_command.add_argument("--workdir", type=Path, default=Path("work"))
    build_command.add_argument("--force", action="store_true", help="rebuild even if the extract is unchanged")
    publish_command = commands.add_parser("publish")
    publish_command.add_argument("code")
    publish_command.add_argument("--bucket", required=True)
    publish_command.add_argument("--workdir", type=Path, default=Path("work"))
    args = parser.parse_args()

    countries = load_countries(COUNTRIES_FILE)
    if args.command == "matrix":
        only = args.only.split()
        if unknown := set(only) - set(countries):
            parser.error(f"unknown countries: {sorted(unknown)}")
        print(json.dumps(only or sorted(countries)))
    elif args.command == "build":
        run_build(countries[args.code], args.bucket, args.workdir, args.force)
    else:
        run_publish(countries[args.code], args.bucket, args.workdir)


if __name__ == "__main__":
    main()
