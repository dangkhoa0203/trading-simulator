"""Triggered on an EventBridge schedule (not invoked by hand). Calls the Flask backend's
/internal/check-alerts endpoint, which holds the actual DB/price logic — kept there instead
of duplicated here so this Lambda needs zero third-party dependencies (no psycopg2 build for
Lambda's Linux runtime to worry about) and there's a single source of truth for the alert
rule.
"""

import json
import os
import urllib.request

API_BASE = os.environ["API_BASE"]
INTERNAL_TASK_SECRET = os.environ["INTERNAL_TASK_SECRET"]


def handler(event, context):
    request = urllib.request.Request(
        f"{API_BASE}/internal/check-alerts",
        method="POST",
        headers={"X-Internal-Secret": INTERNAL_TASK_SECRET},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = json.loads(response.read())

    print(f"check-alerts result: {body}")
    return body
