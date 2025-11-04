# api/ping.py
def handler(request, context):
    return {"statusCode": 200, "body": "pong"}
def handler(request, context):
    return {"statusCode": 200, "body": "pong"}
def handler(request, response):
    response.status_code = 200
    response.send("pong")

