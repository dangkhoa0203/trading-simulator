from functools import wraps

from flask import g, jsonify, request, session

from tokens import verify_token


def resolve_user_id():
    if "user_id" in session:
        return session["user_id"]

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return verify_token(auth_header[len("Bearer ") :])

    return None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = resolve_user_id()
        if user_id is None:
            return jsonify(error="authentication required"), 401
        g.user_id = user_id
        return fn(*args, **kwargs)

    return wrapper
