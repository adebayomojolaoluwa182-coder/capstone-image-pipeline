"""Start one Standard workflow per S3 object-created notification."""
import hashlib
import json
import logging
import os
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

SFN = boto3.client("stepfunctions")
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def lambda_handler(event, context):
    executions = []
    for record in event.get("Records", []):
        if not record.get("eventName", "").startswith("ObjectCreated:"):
            continue
        obj = record["s3"]["object"]
        data = {"bucket": record["s3"]["bucket"]["name"],
                "key": unquote_plus(obj["key"])}
        if obj.get("versionId"):
            data["versionId"] = obj["versionId"]
        if data["bucket"] != os.environ["SOURCE_BUCKET"]:
            raise ValueError("Unexpected source bucket")
        # Duplicate notifications for the same event use the same execution name.
        identity = json.dumps([data, obj.get("sequencer", "")], sort_keys=True)
        name = "s3-" + hashlib.sha256(identity.encode()).hexdigest()
        try:
            result = SFN.start_execution(stateMachineArn=os.environ["STATE_MACHINE_ARN"],
                                         name=name, input=json.dumps(data, sort_keys=True))
            executions.append(result["executionArn"])
            LOG.info("Started workflow for %s: %s", data["key"], result["executionArn"])
        except ClientError as error:
            if error.response["Error"]["Code"] != "ExecutionAlreadyExists":
                raise
            LOG.info("Duplicate S3 event skipped: %s", name)
    return {"executions": executions}
