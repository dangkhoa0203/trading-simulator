from urllib.parse import quote_plus, urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from decorators import resolve_user_id
from extensions import db, oauth
from models import User
from tokens import make_token

bp = Blueprint("auth", __name__)


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()

    if not email or not password or not display_name:
        return jsonify(error="display name, email, and password are all required"), 400

    # Goes straight to Auth0's own signup endpoint — the backend never sees a password land
    # in application code or the database. Only the Auth0 Client ID is needed here (a public
    # identifier, not the client secret), so this is safe to call from an unauthenticated route.
    try:
        resp = requests.post(
            f'https://{current_app.config["AUTH0_DOMAIN"]}/dbconnections/signup',
            json={
                "client_id": current_app.config["AUTH0_CLIENT_ID"],
                "email": email,
                "password": password,
                "connection": "Username-Password-Authentication",
                "name": display_name,
            },
            timeout=10,
        )
    except requests.RequestException:
        return jsonify(error="couldn't reach Auth0 — try again in a moment"), 502

    if resp.ok:
        return jsonify(ok=True), 201

    body = resp.json() if resp.content else {}
    description = body.get("description")
    if isinstance(description, dict) and "rules" in description:
        # PasswordStrengthError puts structured rule data here instead of a string — turn
        # the failed rules into one readable sentence (e.g. "At least 8 characters in length").
        failed = [
            (rule["message"] % tuple(rule["format"])) if rule.get("format") else rule["message"]
            for rule in description["rules"]
            if not rule.get("verified", True)
        ]
        message = "; ".join(failed) or "password doesn't meet the requirements"
    elif isinstance(description, str) and description:
        message = description
    else:
        message = body.get("error_description") or "registration failed"
    return jsonify(error=message), 400


@bp.get("/login")
def login():
    return oauth.auth0.authorize_redirect(redirect_uri=url_for("auth.callback", _external=True))


@bp.get("/callback")
def callback():
    oauth_token = oauth.auth0.authorize_access_token()
    userinfo = oauth_token.get("userinfo") or oauth.auth0.userinfo(token=oauth_token)

    user = User.query.filter_by(auth0_sub=userinfo["sub"]).first()
    if user is None:
        user = User(
            auth0_sub=userinfo["sub"],
            email=userinfo["email"],
            display_name=userinfo.get("name", userinfo["email"]),
        )
        db.session.add(user)
        db.session.commit()

    # Session cookie: works for same-site setups (e.g. local dev). Bearer token: works
    # everywhere else — the frontend and API are on different sites (different AWS public
    # suffixes), so a cross-site cookie gets blocked by Safari ITP / Chrome's third-party
    # cookie phaseout. The frontend picks whichever actually works for it.
    session["user_id"] = user.id
    session["user_email"] = user.email

    if current_app.config["FRONTEND_URL"]:
        auth_token = make_token(user.id)
        return redirect(f'{current_app.config["FRONTEND_URL"]}?token={auth_token}')
    return redirect(url_for("auth.me"))


@bp.get("/logout")
def logout():
    session.clear()
    # request.host_url ignores SCRIPT_NAME (the API Gateway stage prefix ProxyFix injects),
    # so build the API-domain fallback from url_for instead, which does account for it.
    return_to = current_app.config["FRONTEND_URL"] or (
        url_for("auth.login", _external=True).removesuffix("/login") + "/"
    )
    params = urlencode(
        {"returnTo": return_to, "client_id": current_app.config["AUTH0_CLIENT_ID"]},
        quote_via=quote_plus,
    )
    return redirect(f'https://{current_app.config["AUTH0_DOMAIN"]}/v2/logout?{params}')


@bp.get("/me")
def me():
    user_id = resolve_user_id()
    if user_id is None:
        return jsonify(authenticated=False), 401

    user = User.query.get(user_id)
    if user is None:
        return jsonify(authenticated=False), 401

    return jsonify(authenticated=True, user_id=user.id, email=user.email)
