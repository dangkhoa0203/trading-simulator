"""Signed bearer tokens for the frontend to hold, in place of a session cookie.

The frontend and API live on different sites (S3 static website vs API Gateway's
execute-api domain — AWS registers both as separate public suffixes), so a session cookie
is a third-party cookie from the frontend's perspective and gets blocked outright by
Safari's Intelligent Tracking Prevention (and increasingly Chrome). A bearer token sent via
the Authorization header isn't subject to third-party cookie policy at all.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app

TOKEN_SALT = "tradenow-auth-token"
TOKEN_MAX_AGE_SECONDS = 7 * 24 * 3600


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=TOKEN_SALT)


def make_token(user_id):
    return _serializer().dumps({"user_id": user_id})


def verify_token(token):
    try:
        data = _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")
