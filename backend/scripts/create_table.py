"""Create the CrewLog DynamoDB table (only needed if you don't deploy with SAM).

    python scripts/create_table.py --region us-east-1 --table crewlog
"""

import argparse

import boto3

p = argparse.ArgumentParser()
p.add_argument("--region", default="us-east-1")
p.add_argument("--table", default="crewlog")
a = p.parse_args()

ddb = boto3.client("dynamodb", region_name=a.region)
ddb.create_table(
    TableName=a.table,
    BillingMode="PAY_PER_REQUEST",
    AttributeDefinitions=[
        {"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")
    ],
    KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
    GlobalSecondaryIndexes=[
        {
            "IndexName": "GSI1",
            "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}, {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"},
        }
    ],
)
ddb.get_waiter("table_exists").wait(TableName=a.table)
ddb.update_time_to_live(TableName=a.table, TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"})
print(f"created {a.table} in {a.region}")
