"""Create DynamoDB Local tables for development."""

import os
import time

import boto3

ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8001")
REGION = os.environ.get("AWS_REGION", "me-central-1")

TABLES = [
    "travel-ai-leads-dev",
    "travel-ai-bookings-dev",
    "travel-ai-sessions-dev",
    "travel-ai-conversations-dev",
    "travel-ai-price-alerts-dev",
    "travel-ai-events-dev",
    "travel-ai-referrals-dev",
    "travel-ai-itineraries-dev",
]

GSI_TABLES = {
    "travel-ai-leads-dev",
    "travel-ai-bookings-dev",
    "travel-ai-price-alerts-dev",
    "travel-ai-events-dev",
}


def main() -> None:
    client = boto3.client(
        "dynamodb",
        endpoint_url=ENDPOINT,
        region_name=REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
    )

    for _ in range(30):
        try:
            client.list_tables()
            break
        except Exception:
            time.sleep(1)

    existing = client.list_tables().get("TableNames", [])

    for name in TABLES:
        if name in existing:
            print(f"exists: {name}")
            continue

        attrs = [{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}]
        key_schema = [{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}]
        kwargs: dict = {
            "TableName": name,
            "AttributeDefinitions": attrs,
            "KeySchema": key_schema,
            "BillingMode": "PAY_PER_REQUEST",
        }

        if name in GSI_TABLES:
            kwargs["AttributeDefinitions"].extend(
                [{"AttributeName": "GSI1PK", "AttributeType": "S"}, {"AttributeName": "GSI1SK", "AttributeType": "S"}]
            )
            kwargs["GlobalSecondaryIndexes"] = [
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ]

        if name == "travel-ai-sessions-dev":
            kwargs["AttributeDefinitions"] = [{"AttributeName": "PK", "AttributeType": "S"}]
            kwargs["KeySchema"] = [{"AttributeName": "PK", "KeyType": "HASH"}]

        client.create_table(**kwargs)
        print(f"created: {name}")

    print("DynamoDB local tables ready.")


if __name__ == "__main__":
    main()
