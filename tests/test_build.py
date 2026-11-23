import hashlib
import http.server
import tarfile
import threading
import urllib.error

import boto3
import pytest
from moto import mock_aws

from osrm_data import __main__ as cli
from osrm_data import pipeline
from osrm_data.__main__ import COUNTRIES_FILE, is_current, run_build, run_publish
from osrm_data.config import Country, load_countries
from osrm_data.pipeline import (
    BUILD_ONLY_SUFFIXES,
    NOTICE_FILE,
    OSRM_VERSION,
    Build,
    Extract,
    build,
    download,
    notice,
    package,
    resolve,
)
from osrm_data.store import Manifest, Store

COUNTRY = Country(code="kr", name="South Korea", url="https://example.test/kr-latest.osm.pbf", algorithm="ch")
EXTRACT = Extract(url="https://example.test/kr-261122.osm.pbf", md5="abc")


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


@pytest.mark.parametrize("code", ["k", "us-west", "KR", "a" * 17])
def test_a_code_osrm_server_would_reject_is_refused(tmp_path, code):
    path = tmp_path / "countries.yml"
    path.write_text(
        f"source: https://example.test\nalgorithm: ch\ncountries:\n  - {{code: {code}, name: x, extract: x}}\n"
    )
    with pytest.raises(ValueError, match="lowercase"):
        load_countries(path)


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
    def fake_build(country, extract, workdir):
        workdir.mkdir(parents=True)
        archive = workdir / f"{country.code}.tar.zst"
        archive.write_bytes(b"dataset")
        return Build(archive=archive, dataset_bytes=7)

    monkeypatch.setattr(cli, "build", fake_build)
    monkeypatch.setattr(cli, "resolve", lambda url: EXTRACT)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield "test-bucket"


def test_build_touches_nothing_until_publish(bucket, tmp_path):
    assert run_build(COUNTRY, bucket, tmp_path, force=False) == "built"
    assert Store(bucket).latest("kr") is None

    assert run_publish(COUNTRY, bucket, tmp_path) == "published"
    published = Store(bucket).latest("kr")
    assert published is not None and (published.source_url, published.source_md5) == (EXTRACT.url, "abc")
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

    assert package(base, archive, threads=1, notice_text=notice(COUNTRY, EXTRACT)) == 5
    with tarfile.open(archive) as tar:
        assert tar.getnames() == ["kr.osrm.hsgr", NOTICE_FILE]


def test_an_archive_carries_the_data_license_and_credit(tmp_path):
    """The datasets are OpenStreetMap's data under ODbL, not Apache like this repository's code."""
    base = tmp_path / "kr.osrm"
    base.with_name("kr.osrm.hsgr").write_bytes(b"12345")
    archive = tmp_path / "out.tar.zst"

    package(base, archive, threads=1, notice_text=notice(COUNTRY, EXTRACT))
    with tarfile.open(archive) as tar:
        member = tar.extractfile(NOTICE_FILE)
        assert member is not None
        text = member.read().decode()

    assert "© OpenStreetMap contributors" in text
    assert "https://opendatacommons.org/licenses/odbl/1-0/" in text
    assert EXTRACT.url in text


def test_a_manifest_names_the_data_license():
    assert (_manifest().license, _manifest().attribution) == ("ODbL-1.0", "© OpenStreetMap contributors")


class ExtractServer(http.server.BaseHTTPRequestHandler):
    """Serves `-latest` the way the extract server does: as a redirect to a dated file."""

    dated = b"dated extract"
    # While an extract is being published, `-latest.md5` can already describe the next one.
    files = {
        "/kr/kr-261122.osm.pbf": dated,
        "/kr/kr-261122.osm.pbf.md5": f"{hashlib.md5(dated).hexdigest()}  kr-261122.osm.pbf\n".encode(),
        "/kr/kr-latest.osm.pbf.md5": b"0123456789abcdef0123456789abcdef  kr-latest.osm.pbf\n",
    }
    # Paths to answer with 503 this many more times, then normally.
    failures: dict[str, int] = {}

    def do_HEAD(self):
        self.respond(body=False)

    def do_GET(self):
        self.respond(body=True)

    def respond(self, body: bool):
        if self.failures.get(self.path, 0) > 0:
            self.failures[self.path] -= 1
            self.send_error(503)
        elif self.path == "/kr-latest.osm.pbf":
            self.redirect(301, "/kr/kr-latest.osm.pbf")
        elif self.path == "/kr/kr-latest.osm.pbf":
            self.redirect(307, "/kr/kr-261122.osm.pbf")
        elif content := self.files.get(self.path):
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if body:
                self.wfile.write(content)
        else:
            self.send_error(404)

    def redirect(self, code: int, location: str):
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(pipeline, "RETRY_DELAYS", (0, 0))
    monkeypatch.setattr(ExtractServer, "failures", {})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ExtractServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join()


def test_resolve_pins_the_dated_file_and_its_own_checksum(server):
    extract = resolve(f"{server}/kr-latest.osm.pbf")
    assert extract == Extract(url=f"{server}/kr/kr-261122.osm.pbf", md5=hashlib.md5(ExtractServer.dated).hexdigest())


def test_a_download_outlasts_passing_server_errors(server, tmp_path):
    ExtractServer.failures.update({"/kr-latest.osm.pbf": 1, "/kr/kr-261122.osm.pbf.md5": 1})
    extract = resolve(f"{server}/kr-latest.osm.pbf")
    ExtractServer.failures["/kr/kr-261122.osm.pbf"] = 2
    download(extract, tmp_path / "kr.osm.pbf")
    assert (tmp_path / "kr.osm.pbf").read_bytes() == ExtractServer.dated


def test_a_download_gives_up_after_the_last_retry(server, tmp_path):
    ExtractServer.failures["/kr/kr-261122.osm.pbf"] = 3
    with pytest.raises(urllib.error.HTTPError):
        download(Extract(url=f"{server}/kr/kr-261122.osm.pbf", md5="x"), tmp_path / "kr.osm.pbf")


def test_a_download_that_keeps_mismatching_fails(server, tmp_path):
    with pytest.raises(pipeline.ChecksumMismatch):
        download(Extract(url=f"{server}/kr/kr-261122.osm.pbf", md5="0" * 32), tmp_path / "kr.osm.pbf")


@pytest.mark.e2e
@pytest.mark.parametrize("algorithm", ["ch", "mld"])
def test_built_archive_answers_queries(tmp_path, algorithm):
    import osrm

    url = "https://download.geofabrik.de/europe/monaco-latest.osm.pbf"
    country = Country(code="mc", name="Monaco", url=url, algorithm=algorithm)
    result = build(country, resolve(url), tmp_path / "build")

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
