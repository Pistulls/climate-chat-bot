"""S3 Vectors helpers shared by ingestion (put, list, delete) and the service (query).

One `VectorIndex` wraps one index in one vector bucket. Batches respect the service limit of
500 vectors per PutVectors or DeleteVectors call.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from climate_chat.config import Settings

BATCH = 500  # S3 Vectors limit per PutVectors / DeleteVectors call


@dataclass(frozen=True)
class Record:
    key: str
    vector: np.ndarray
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Match:
    key: str
    distance: float
    metadata: dict[str, Any]


def batches(items: Sequence, size: int = BATCH) -> Iterator[Sequence]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def s3vectors_client(settings: Settings) -> Any:
    from botocore.config import Config

    return settings.aws_client(
        "s3vectors", config=Config(retries={"mode": "adaptive", "total_max_attempts": 8})
    )


class VectorIndex:
    def __init__(self, bucket: str, index: str, client: Any):
        self.bucket, self.index, self.client = bucket, index, client

    @classmethod
    def sources(cls, settings: Settings, client: Any | None = None) -> VectorIndex:
        return cls(
            settings.vector_bucket,
            settings.sources_index,
            client or s3vectors_client(settings),
        )

    def _where(self) -> dict[str, str]:
        return {"vectorBucketName": self.bucket, "indexName": self.index}

    def dimension(self) -> int:
        return self.client.get_index(**self._where())["index"]["dimension"]

    def keys(self) -> list[str]:
        """Every key in the index. ListVectors has no prefix filter, so callers filter."""
        paginator = self.client.get_paginator("list_vectors")
        return list(paginator.paginate(**self._where()).search("vectors[].key"))

    def put(self, records: Sequence[Record]) -> int:
        for batch in batches(records):
            self.client.put_vectors(
                **self._where(),
                vectors=[
                    {
                        "key": r.key,
                        "data": {"float32": np.asarray(r.vector, dtype=np.float32).tolist()},
                        "metadata": r.metadata,
                    }
                    for r in batch
                ],
            )
        return len(records)

    def delete(self, keys: Iterable[str]) -> int:
        keys = list(keys)
        for batch in batches(keys):
            self.client.delete_vectors(**self._where(), keys=list(batch))
        return len(keys)

    def query(
        self,
        vector: np.ndarray,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[Match]:
        kwargs: dict[str, Any] = {
            **self._where(),
            "queryVector": {"float32": np.asarray(vector, dtype=np.float32).tolist()},
            "topK": top_k,
            "returnMetadata": True,
            "returnDistance": True,
        }
        if filter:
            kwargs["filter"] = filter
        response = self.client.query_vectors(**kwargs)
        return [
            Match(v["key"], float(v.get("distance", 0.0)), v.get("metadata", {}))
            for v in response.get("vectors", [])
        ]
