from flask import Flask, redirect, url_for

from app.config import Config
from app.database import init_app, init_db
from app.routes.empresas import empresas_bp
from app.routes.historico import historico_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db()
    init_app(app)

    app.register_blueprint(empresas_bp)
    app.register_blueprint(historico_bp)

    @app.route("/")
    def index():
        return redirect(url_for("empresas.index"))

    return app
