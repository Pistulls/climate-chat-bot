"""Placeholder for the Climate Chat API until the service is deployed.

Returns 503 for every request and logs the client IP header, so the CloudFront ->
function URL path and the IP forwarding can be checked end to end.
"""

import json


def handler(event: dict, context: object) -> dict:
    headers = event.get("headers") or {}
    print(json.dumps({
        "msg": "placeholder",
        "path": event.get("rawPath"),
        "cloudfront_viewer_address": headers.get("cloudfront-viewer-address"),
    }))
    return {
        "statusCode": 503,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": "not deployed"}),
    }
