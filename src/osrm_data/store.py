"""Publishes datasets to S3.

Layout under the bucket:

    <code>/latest.json                   the manifest readers start from
    <code>/<version>/<code>.tar.zst      an immutable dataset

Readers follow `latest.json`, and it is written last, so a reader never sees a
half-uploaded dataset. A few older versions stay behind for a reader that is
still downloading one and for rolling back.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

KEEP_VERSIONS = 3

# Larger parts than the 8 MiB default: a dataset takes far fewer requests.
TRANSFER = TransferConfig(multipart_chunksize=64 * 2**20, multipart_threshold=64 * 2**20)


@dataclass(frozen=True)
class Manifest:
    country: str
    version: str
    algorithm: str
    osrm_version: str
    archive_key: str
    archive_bytes: int
    archive_sha256: str
    dataset_bytes: int
    source_url: str
    source_md5: str
    built_at: str
    stages: dict[str, dict[str, float]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


class Store:
    def __init__(self, bucket: str, client=None) -> None:
        self.bucket = bucket
        self.s3 = client or boto3.client("s3")

    def latest(self, code: str) -> Manifest | None:
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=f"{code}/latest.json")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        return Manifest(**json.loads(response["Body"].read()))

    def publish(self, archive: Path, manifest: Manifest) -> Manifest:
        self.s3.upload_file(str(archive), self.bucket, manifest.archive_key, Config=TRANSFER)
        self.s3.put_object(
            Bucket=self.bucket,
            Key=f"{manifest.country}/latest.json",
            Body=json.dumps(asdict(manifest), indent=2).encode(),
            ContentType="application/json",
        )
        self.prune(manifest.country)
        return manifest

    def prune(self, code: str) -> list[str]:
        pages = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=f"{code}/")
        keys = [item["Key"] for page in pages for item in page.get("Contents", [])]
        # Versions are UTC timestamps, so they sort by age.
        versions = sorted({key.split("/")[1] for key in keys if key.count("/") == 2})
        stale = set(versions[:-KEEP_VERSIONS])
        removed = [key for key in keys if key.count("/") == 2 and key.split("/")[1] in stale]
        for key in removed:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        return removed


def manifest_for(
    *,
    code: str,
    version: str,
    algorithm: str,
    osrm_version: str,
    archive: Path,
    dataset_bytes: int,
    source_url: str,
    source_md5: str,
    built_at: str,
    stages: dict[str, dict[str, float]],
) -> Manifest:
    return Manifest(
        country=code,
        version=version,
        algorithm=algorithm,
        osrm_version=osrm_version,
        archive_key=f"{code}/{version}/{code}.tar.zst",
        archive_bytes=archive.stat().st_size,
        archive_sha256=_sha256(archive),
        dataset_bytes=dataset_bytes,
        source_url=source_url,
        source_md5=source_md5,
        built_at=built_at,
        stages=stages,
    )
