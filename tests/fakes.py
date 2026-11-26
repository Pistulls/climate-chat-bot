"""Test doubles shared across test modules."""


class FakePaginator:
    def __init__(self, keys, page=3):
        self.keys, self.page = keys, page

    def paginate(self, **kwargs):
        pages = [
            {"vectors": [{"key": k} for k in self.keys[i : i + self.page]]}
            for i in range(0, len(self.keys), self.page)
        ]

        class Result:
            def search(self, expression):
                assert expression == "vectors[].key"
                return (v["key"] for p in pages for v in p["vectors"])

        return Result()


class FakeS3Vectors:
    """Records calls; holds vectors in a dict keyed by vector key."""

    def __init__(self, dimension=3):
        self.calls, self.stored, self.dimension = [], {}, dimension

    def get_index(self, **kwargs):
        return {"index": {"dimension": self.dimension}}

    def get_paginator(self, name):
        assert name == "list_vectors"
        return FakePaginator(sorted(self.stored))

    def put_vectors(self, **kwargs):
        self.calls.append(("put", kwargs))
        for v in kwargs["vectors"]:
            self.stored[v["key"]] = v

    def delete_vectors(self, **kwargs):
        self.calls.append(("delete", kwargs))
        for k in kwargs["keys"]:
            self.stored.pop(k, None)

    def query_vectors(self, **kwargs):
        self.calls.append(("query", kwargs))
        return {
            "vectors": [
                {"key": "05-0001", "distance": 0.1, "metadata": {"source_id": "05"}},
                {"key": "12-0003", "distance": 0.2, "metadata": {"source_id": "12"}},
            ]
        }


class FakeLogTable:
    """Holds items like the logs table: pk = day#YYYY-MM-DD, sk = time#request id.
    `query` mimics DynamoDB: one partition, sorted by sk, Limit and LastEvaluatedKey."""

    def __init__(self, items):
        self.items = items
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        pk = kwargs["ExpressionAttributeValues"][":pk"]
        rows = sorted(
            (i for i in self.items if i["pk"] == pk),
            key=lambda i: i["sk"],
            reverse=not kwargs.get("ScanIndexForward", True),
        )
        start = kwargs.get("ExclusiveStartKey")
        if start:
            rows = rows[[r["sk"] for r in rows].index(start["sk"]) + 1 :]
        limit = kwargs["Limit"]
        page = rows[:limit]
        result = {"Items": page}
        if len(rows) > limit:
            result["LastEvaluatedKey"] = {"pk": pk, "sk": page[-1]["sk"]}
        return result
