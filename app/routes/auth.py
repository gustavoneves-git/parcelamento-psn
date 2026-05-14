from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("autenticado"):
        return redirect(_destino_pos_login())

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""

        if not _login_configurado():
            flash("Login do sistema ainda nao foi configurado no servidor.", "error")
        elif _credenciais_validas(usuario, senha):
            session.clear()
            session.permanent = True
            session["autenticado"] = True
            session["usuario"] = usuario
            return redirect(_destino_pos_login())
        else:
            flash("Usuario ou senha invalidos.", "error")

    return render_template("login.html", next=request.args.get("next", ""))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sessao encerrada com sucesso.", "success")
    return redirect(url_for("auth.login"))


def _login_configurado():
    return bool(
        current_app.config.get("APP_LOGIN_USER")
        and current_app.config.get("APP_LOGIN_PASSWORD_HASH")
    )


def _credenciais_validas(usuario, senha):
    usuario_configurado = current_app.config["APP_LOGIN_USER"]
    hash_configurado = current_app.config["APP_LOGIN_PASSWORD_HASH"]
    return usuario == usuario_configurado and check_password_hash(hash_configurado, senha)


def _destino_pos_login():
    destino = request.args.get("next") or request.form.get("next") or url_for("empresas.index")
    if not destino.startswith("/") or destino.startswith("//"):
        return url_for("empresas.index")
    if destino.startswith(url_for("auth.login")):
        return url_for("empresas.index")
    return destino
