import json

import boto3
import pytest
from moto import mock_aws

from osrm_data.store import KEEP_VERSIONS, Store, manifest_for

BUCKET = "test-bucket"


@pytest.fixture
def store():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield Store(BUCKET, client=client)


def _publish(store, tmp_path, version):
    archive = tmp_path / "kr.tar.zst"
    archive.write_bytes(version.encode())
    manifest = manifest_for(
        code="kr",
        version=version,
        algorithm="ch",
        osrm_version="26.10.0",
        archive=archive,
        dataset_bytes=10,
        source_url="https://example.test/kr.osm.pbf",
        source_md5="abc",
        built_at="2026-10-31T00:00:00+00:00",
        stages={},
    )
    return store.publish(archive, manifest)


def test_latest_is_none_before_the_first_build(store):
    assert store.latest("kr") is None


def test_publish_round_trips_the_manifest(store, tmp_path):
    manifest = _publish(store, tmp_path, "20261031T180000Z")
    assert store.latest("kr") == manifest
    body = store.s3.get_object(Bucket=BUCKET, Key=manifest.archive_key)["Body"].read()
    assert body == b"20261031T180000Z"


def test_prune_keeps_recent_versions_and_the_manifest(store, tmp_path):
    versions = [f"2026103{day}T180000Z" for day in range(KEEP_VERSIONS + 2)]
    for version in versions:
        _publish(store, tmp_path, version)

    keys = {item["Key"] for item in store.s3.list_objects_v2(Bucket=BUCKET)["Contents"]}
    assert keys == {"kr/latest.json"} | {f"kr/{v}/kr.tar.zst" for v in versions[-KEEP_VERSIONS:]}
    assert (
        json.loads(store.s3.get_object(Bucket=BUCKET, Key="kr/latest.json")["Body"].read())["version"] == versions[-1]
    )


def test_prune_leaves_other_countries_alone(store):
    store.s3.put_object(Bucket=BUCKET, Key="kr2/20260101T000000Z/kr2.tar.zst", Body=b"x")
    assert store.prune("kr") == []
    assert store.s3.get_object(Bucket=BUCKET, Key="kr2/20260101T000000Z/kr2.tar.zst")
