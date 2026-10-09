from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from alerts import bp as alerts_bp
from auth import bp as auth_bp
from config import Config
from extensions import db, oauth
from market_routes import bp as market_bp
from portfolios import bp as portfolios_bp
from reports import bp as reports_bp
from statements import bp as statements_bp
from trades import bp as trades_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Behind API Gateway (HTTP_PROXY integration): trust X-Forwarded-Host/Proto/For so
    # url_for(_external=True) builds URLs (e.g. the Auth0 redirect_uri) using the URL the
    # client actually called, not this instance's own EB hostname/scheme.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    if app.config["CORS_ORIGINS"]:
        CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    db.init_app(app)
    oauth.init_app(app)
    oauth.register(
        "auth0",
        client_id=app.config["AUTH0_CLIENT_ID"],
        client_secret=app.config["AUTH0_CLIENT_SECRET"],
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f'https://{app.config["AUTH0_DOMAIN"]}/.well-known/openid-configuration',
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolios_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(statements_bp)

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="tradenow-backend")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
