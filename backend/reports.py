"""Reads the EMR job's output (moving averages / trend report) from S3 for the dashboard.
The Spark job (emr/moving_average_job.py) writes line-delimited JSON via coalesce(1), so
each report is a single part-*.json file under a known prefix — list then read it.
"""

import json

import boto3
from flask import Blueprint, current_app, jsonify

from decorators import login_required

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _read_json_lines(prefix):
    s3 = _s3_client()
    bucket = current_app.config["EMR_REPORTS_BUCKET"]
    objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    rows = []
    for obj in objects.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".json"):
            continue
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        for line in body.splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


@bp.get("/latest")
@login_required
def latest():
    try:
        rows = _read_json_lines("reports/latest/")
    except Exception as exc:
        return jsonify(error=f"EMR report not available yet: {exc}"), 404
    return jsonify(rows)


@bp.get("/series/<symbol>")
@login_required
def series(symbol):
    try:
        rows = _read_json_lines("reports/series/")
    except Exception as exc:
        return jsonify(error=f"EMR report not available yet: {exc}"), 404
    filtered = sorted(
        (r for r in rows if r.get("symbol", "").upper() == symbol.upper()),
        key=lambda r: r.get("date", ""),
    )
    return jsonify(symbol=symbol.upper(), series=filtered)
