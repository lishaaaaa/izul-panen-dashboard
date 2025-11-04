# api/ping.py
def handler(request, context):
    return {"statusCode": 200, "body": "pong"}
