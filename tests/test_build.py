import tarfile

import boto3
import pytest
from moto import mock_aws

from osrm_data import __main__ as cli
from osrm_data.__main__ import COUNTRIES_FILE, is_current, run_build, run_publish
from osrm_data.config import Country, load_countries
from osrm_data.pipeline import BUILD_ONLY_SUFFIXES, OSRM_VERSION, Build, build, fetch_md5, package
from osrm_data.store import Manifest, Store

COUNTRY = Country(code="kr", name="South Korea", url="https://example.test/kr.osm.pbf", algorithm="ch")


def _manifest(**overrides):
    values = {
        "country": "kr",
        "version": "20261031T180000Z",
        "algorithm": "ch",
        "osrm_version": OSRM_VERSION,
        "archive_key": "kr/20261031T180000Z/kr.tar.zst",
        "archive_bytes": 1,
        "archive_sha256": "x",
        "dataset_bytes": 1,
        "source_url": COUNTRY.url,
        "source_md5": "abc",
        "built_at": "2026-10-31T18:00:00+00:00",
        "stages": {},
    }
    return Manifest(**(values | overrides))


def test_countries_file_is_valid():
    countries = load_countries(COUNTRIES_FILE)
    assert countries["kr"].url.endswith("/asia/south-korea-latest.osm.pbf")


@pytest.mark.parametrize(
    ("manifest", "md5", "expected"),
    [
        (None, "abc", False),
        (_manifest(), "abc", True),
        (_manifest(), "changed", False),
        (_manifest(algorithm="mld"), "abc", False),
        # A new OSRM release must rebuild data even when the map did not change.
        (_manifest(osrm_version="0.0.0"), "abc", False),
    ],
)
def test_is_current(manifest, md5, expected):
    assert is_current(manifest, COUNTRY, md5) is expected


@pytest.fixture
def bucket(monkeypatch):
    def fake_build(country, md5, workdir):
        workdir.mkdir(parents=True)
        archive = workdir / f"{country.code}.tar.zst"
        archive.write_bytes(b"dataset")
        return Build(archive=archive, dataset_bytes=7)

    monkeypatch.setattr(cli, "build", fake_build)
    monkeypatch.setattr(cli, "fetch_md5", lambda url: "abc")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield "test-bucket"


def test_build_touches_nothing_until_publish(bucket, tmp_path):
    assert run_build(COUNTRY, bucket, tmp_path, force=False) == "built"
    assert Store(bucket).latest("kr") is None

    assert run_publish(COUNTRY, bucket, tmp_path) == "published"
    published = Store(bucket).latest("kr")
    assert published is not None and published.source_md5 == "abc"
    assert Store(bucket).s3.get_object(Bucket=bucket, Key=published.archive_key)["Body"].read() == b"dataset"


def test_a_skipped_build_leaves_nothing_to_publish(bucket, tmp_path):
    run_build(COUNTRY, bucket, tmp_path, force=False)
    run_publish(COUNTRY, bucket, tmp_path)

    assert run_build(COUNTRY, bucket, tmp_path, force=False) == "skipped"
    assert run_publish(COUNTRY, bucket, tmp_path) == "skipped"


def test_package_leaves_out_build_only_files(tmp_path):
    base = tmp_path / "kr.osrm"
    base.with_name("kr.osrm.hsgr").write_bytes(b"12345")
    base.with_name("kr.osrm.ebg").write_bytes(b"x" * 100)
    # Same prefix, different dataset: must not be swept into this archive.
    (tmp_path / "kr.osrm2.hsgr").write_bytes(b"other")
    archive = tmp_path / "out.tar.zst"

    assert package(base, archive, threads=1) == 5
    with tarfile.open(archive) as tar:
        assert tar.getnames() == ["kr.osrm.hsgr"]


@pytest.mark.e2e
@pytest.mark.parametrize("algorithm", ["ch", "mld"])
def test_built_archive_answers_queries(tmp_path, algorithm):
    import osrm

    url = "https://download.geofabrik.de/europe/monaco-latest.osm.pbf"
    country = Country(code="mc", name="Monaco", url=url, algorithm=algorithm)
    result = build(country, fetch_md5(url), tmp_path / "build")

    served = tmp_path / "served"
    with tarfile.open(result.archive) as tar:
        tar.extractall(served, filter="data")
    assert not [p for p in served.iterdir() if p.name.removeprefix("mc.osrm") in BUILD_ONLY_SUFFIXES]

    engine = osrm.OSRM(
        storage_config=str(served / "mc.osrm"),
        algorithm=algorithm.upper(),
        use_shared_memory=False,
        use_mmap=True,
    )
    coordinates = [(7.41337, 43.72956), (7.41546, 43.73077)]
    assert engine.Table(osrm.TableParameters(coordinates=coordinates))["code"] == "Ok"
    assert engine.Route(osrm.RouteParameters(coordinates=coordinates))["code"] == "Ok"
