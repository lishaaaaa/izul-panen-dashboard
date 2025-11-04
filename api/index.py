# api/index.py
from app import app
from serverless_wsgi import handle_request

def handler(request, context):
    return handle_request(app, request, context)
