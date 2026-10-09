"""Triggered by an S3 ObjectCreated event on the raw-data bucket (new historical price
data landed by backend/fetch_historical_data.py). Launches a fresh, auto-terminating EMR
cluster running emr/moving_average_job.py — no manual "Add Step" via the console, and no
idle cluster left running: KeepJobFlowAliveWhenNoSteps=False shuts it down the moment the
step finishes.
"""

import os
import time

import boto3

emr = boto3.client("emr")

RAW_BUCKET = os.environ["RAW_BUCKET"]
REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
SCRIPT_S3_PATH = os.environ["SCRIPT_S3_PATH"]
EMR_RELEASE_LABEL = os.environ.get("EMR_RELEASE_LABEL", "emr-7.5.0")
EMR_SERVICE_ROLE = os.environ.get("EMR_SERVICE_ROLE", "EMR_DefaultRole")
EMR_INSTANCE_PROFILE = os.environ.get("EMR_INSTANCE_PROFILE", "EMR_EC2_DefaultRole")
EMR_INSTANCE_TYPE = os.environ.get("EMR_INSTANCE_TYPE", "m5.xlarge")


def handler(event, context):
    response = emr.run_job_flow(
        Name=f"tradenow-moving-averages-{int(time.time())}",
        ReleaseLabel=EMR_RELEASE_LABEL,
        Applications=[{"Name": "Spark"}],
        Instances={
            "InstanceGroups": [
                {
                    "Name": "Master",
                    "Market": "ON_DEMAND",
                    "InstanceRole": "MASTER",
                    "InstanceType": EMR_INSTANCE_TYPE,
                    "InstanceCount": 1,
                }
            ],
            "KeepJobFlowAliveWhenNoSteps": False,
            "TerminationProtected": False,
        },
        Steps=[
            {
                "Name": "MovingAverageJob",
                "ActionOnFailure": "TERMINATE_CLUSTER",
                "HadoopJarStep": {
                    "Jar": "command-runner.jar",
                    "Args": ["spark-submit", SCRIPT_S3_PATH, RAW_BUCKET, REPORTS_BUCKET],
                },
            }
        ],
        VisibleToAllUsers=True,
        JobFlowRole=EMR_INSTANCE_PROFILE,
        ServiceRole=EMR_SERVICE_ROLE,
        LogUri=f"s3://{REPORTS_BUCKET}/emr-logs/",
    )

    cluster_id = response["JobFlowId"]
    print(f"Started EMR cluster {cluster_id} for event: {event}")
    return {"jobFlowId": cluster_id}
