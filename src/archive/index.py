import json, os, boto3
DDB = boto3.client("dynamodb")

def handler(event, context):
    items = []
    kwargs = {"TableName": os.environ["TABLE"]}
    while True:
        r = DDB.scan(**kwargs)
        items += r["Items"]
        if "LastEvaluatedKey" not in r:
            break
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    runs = sorted(
        ({"run_date": i["run_date"]["S"],
          "run_at_utc": i.get("run_at_utc", {}).get("S", ""),
          "candidates": int(i.get("candidates", {}).get("N", "0")),
          "brief": i.get("brief", {}).get("S", "")} for i in items),
        key=lambda x: x["run_date"], reverse=True)
    return {"statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"runs": runs})}
