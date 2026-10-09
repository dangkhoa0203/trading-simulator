import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///tradenow.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")

    AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
    AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID")
    AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET")

    MARKET_API_KEY = os.environ.get("MARKET_API_KEY")

    # Shared secret guarding /internal/check-alerts — that route runs unauthenticated
    # (called by the Lambda trigger, not a logged-in browser), so this is its only gate.
    INTERNAL_TASK_SECRET = os.environ.get("INTERNAL_TASK_SECRET", "")

    # ECS-hosted PDF rendering microservice (behind its own ALB). Empty in local dev unless
    # the ALB is currently up — see docs/day8_ecs.md for redeploying it on demand.
    PDF_SERVICE_URL = os.environ.get("PDF_SERVICE_URL", "")

    MARKET_DATA_BUCKET = os.environ.get("MARKET_DATA_BUCKET", "tradenow-raw-market-data-561641367291")
    EMR_REPORTS_BUCKET = os.environ.get("EMR_REPORTS_BUCKET", "tradenow-emr-reports-561641367291")
    STATIC_ASSETS_BUCKET = os.environ.get("STATIC_ASSETS_BUCKET", "tradenow-static-assets-561641367291")

    # Where /callback sends the browser after a successful login. Falls back to /me
    # (JSON) if unset, so local dev without this configured still shows something useful.
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

    # Frontend origin(s) allowed to call this API cross-site, e.g. the S3/CloudFront
    # frontend URL. Comma-separated. Empty in local dev (same-origin, no CORS needed).
    CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o]

    # Cross-site cookies (frontend on a different origin than the API) require
    # SameSite=None + Secure, which only works over HTTPS. Local dev stays Lax/insecure.
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
