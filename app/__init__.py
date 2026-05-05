from flask import Flask, redirect, render_template, url_for
from werkzeug.exceptions import HTTPException

from app.config import Config
from app.database import init_app, init_db
from app.routes.empresas import empresas_bp
from app.routes.historico import historico_bp
from app.services.erro_interno_service import registrar_erro_interno


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

    @app.errorhandler(Exception)
    def tratar_erro_interno(exc):
        if isinstance(exc, HTTPException):
            return exc

        codigo_ocorrencia = registrar_erro_interno(exc)
        return (
            render_template(
                "erro_interno.html",
                codigo_ocorrencia=codigo_ocorrencia,
            ),
            500,
        )

    return app
