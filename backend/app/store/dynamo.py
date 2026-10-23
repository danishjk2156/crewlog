"""DynamoDB single-table store.

PK/SK layout (see TECHNICAL_PLAN.md §9):
  JOB#<id>  META                     job
  JOB#<id>  EVT#<ts13>#<event_id>    event
  JOB#<id>  DIG#<date>               digest
  JOB#<id>  ALR#<date>#<kind>#<id>   alert
  REQ#<key> REQ                      dedupe marker (TTL 7 days)
Jobs also carry GSI1PK = "JOBS" so all jobs can be listed with one Query.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..models import Alert, Digest, Job, RingEvent
from .base import Store


def _clean(obj):
    """Round-trip through JSON so Decimals become int/float again."""
    return json.loads(json.dumps(obj, default=lambda d: int(d) if d == int(d) else float(d)))


def _dyn(obj):
    return json.loads(json.dumps(obj), parse_float=Decimal)


class DynamoStore(Store):
    def __init__(self, table_name: str, region: str):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    # jobs
    def put_job(self, job: Job) -> None:
        item = {"PK": f"JOB#{job.id}", "SK": "META", "GSI1PK": "JOBS", "GSI1SK": str(job.created_at), "data": _dyn(job.model_dump())}
        self.table.put_item(Item=item)

    def get_job(self, job_id: str) -> Job | None:
        item = self.table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "META"}).get("Item")
        return Job(**_clean(item["data"])) if item else None

    def list_jobs(self) -> list[Job]:
        resp = self.table.query(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("JOBS"))
        return [Job(**_clean(i["data"])) for i in resp.get("Items", [])]

    # events
    def _claim(self, key: str) -> bool:
        try:
            self.table.put_item(
                Item={"PK": f"REQ#{key}", "SK": "REQ", "ttl": int(time.time()) + 7 * 86400},
                ConditionExpression="attribute_not_exists(PK)",
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def add_event(self, event: RingEvent) -> bool:
        if not self._claim(f"id:{event.id}"):
            return False
        if event.request_id and not self._claim(f"rq:{event.request_id}"):
            return False
        self.table.put_item(
            Item={"PK": f"JOB#{event.job_id}", "SK": f"EVT#{event.ts_ms:013d}#{event.id}", "data": _dyn(event.model_dump())}
        )
        return True

    def events_between(self, job_id: str, start_ms: int, end_ms: int) -> list[RingEvent]:
        out, kwargs = [], {
            "KeyConditionExpression": Key("PK").eq(f"JOB#{job_id}")
            & Key("SK").between(f"EVT#{start_ms:013d}", f"EVT#{end_ms - 1:013d}#~"),
        }
        while True:
            resp = self.table.query(**kwargs)
            out.extend(RingEvent(**_clean(i["data"])) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return out
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    # digests
    def put_digest(self, digest: Digest) -> None:
        self.table.put_item(Item={"PK": f"JOB#{digest.job_id}", "SK": f"DIG#{digest.date}", "data": _dyn(digest.model_dump())})

    def get_digest(self, job_id: str, day: str) -> Digest | None:
        item = self.table.get_item(Key={"PK": f"JOB#{job_id}", "SK": f"DIG#{day}"}).get("Item")
        return Digest(**_clean(item["data"])) if item else None

    # alerts
    def put_alert(self, alert: Alert) -> None:
        self.table.put_item(
            Item={"PK": f"JOB#{alert.job_id}", "SK": f"ALR#{alert.date}#{alert.kind}#{alert.id}", "data": _dyn(alert.model_dump())}
        )

    def list_alerts(self, job_id: str) -> list[Alert]:
        resp = self.table.query(KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("ALR#"))
        alerts = [Alert(**_clean(i["data"])) for i in resp.get("Items", [])]
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def reset(self) -> None:
        raise NotImplementedError("reset is disabled for DynamoDB; delete items manually")
