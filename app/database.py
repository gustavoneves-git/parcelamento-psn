import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db_path():
    try:
        return Path(current_app.config["DATABASE_PATH"])
    except RuntimeError:
        from app.config import Config

        return Path(Config.DATABASE_PATH)


def get_db():
    if "db" not in g:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                nome_empresa TEXT NOT NULL,
                nome_onvio TEXT,
                pasta_onvio TEXT,
                status_empresa TEXT NOT NULL DEFAULT 'ATIVA'
                    CHECK (status_empresa IN ('ATIVA', 'INATIVA')),
                observacao TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS parcelas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                valor REAL,
                vencimento TEXT,
                caminho_pdf TEXT,
                status_emissao TEXT NOT NULL DEFAULT 'NAO_EMITIDA'
                    CHECK (status_emissao IN (
                        'NAO_EMITIDA',
                        'AGUARDANDO_API',
                        'EMITIDA',
                        'ERRO_EMISSAO'
                    )),
                status_onvio TEXT NOT NULL DEFAULT 'NAO_DISPONIVEL'
                    CHECK (status_onvio IN (
                        'NAO_DISPONIVEL',
                        'PRONTO_PARA_SUBIR',
                        'ENVIADO',
                        'ERRO_ONVIO'
                    )),
                mensagem TEXT,
                data_emissao TEXT,
                data_envio_onvio TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (empresa_id, competencia),
                FOREIGN KEY (empresa_id) REFERENCES empresas (id)
            );

            CREATE TABLE IF NOT EXISTS serpro_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                competencia TEXT,
                acao TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('INFO', 'SUCESSO', 'ERRO')),
                http_status INTEGER,
                mensagem TEXT NOT NULL,
                detalhe_tecnico TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas (id)
            );

            CREATE TABLE IF NOT EXISTS psn_disponibilidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                competencia TEXT NOT NULL,
                parcela_aaaamm TEXT NOT NULL,
                valor REAL,
                status_disponibilidade TEXT NOT NULL
                    CHECK (status_disponibilidade IN (
                        'DISPONIVEL',
                        'INDISPONIVEL',
                        'ERRO_CONSULTA'
                    )),
                mensagem TEXT,
                resposta_resumo TEXT,
                data_consulta TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (empresa_id, parcela_aaaamm),
                FOREIGN KEY (empresa_id) REFERENCES empresas (id)
            );

            CREATE TABLE IF NOT EXISTS erros_internos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_ocorrencia TEXT NOT NULL UNIQUE,
                sistema TEXT NOT NULL,
                versao_sistema TEXT,
                empresa_id INTEGER,
                usuario TEXT,
                tela TEXT,
                acao TEXT,
                rota TEXT,
                metodo_http TEXT,
                competencia TEXT,
                tipo_erro TEXT NOT NULL,
                mensagem_erro TEXT,
                detalhe_tecnico TEXT,
                stack_trace TEXT,
                contexto_json TEXT,
                email_enviado INTEGER NOT NULL DEFAULT 0,
                email_erro TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas (id)
            );

            CREATE TABLE IF NOT EXISTS onvio_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                parcela_id INTEGER,
                acao TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('INFO', 'SUCESSO', 'ERRO')),
                mensagem TEXT NOT NULL,
                detalhe_tecnico TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas (id),
                FOREIGN KEY (parcela_id) REFERENCES parcelas (id)
            );

            CREATE TABLE IF NOT EXISTS onvio_fila (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL,
                parcela_id INTEGER NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN (
                        'AGUARDANDO',
                        'PROCESSANDO',
                        'SUCESSO',
                        'ERRO'
                    )),
                tentativas INTEGER NOT NULL DEFAULT 0,
                mensagem TEXT,
                data_criacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data_inicio TEXT,
                data_fim TEXT,
                data_atualizacao TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (empresa_id) REFERENCES empresas (id),
                FOREIGN KEY (parcela_id) REFERENCES parcelas (id)
            );

            CREATE INDEX IF NOT EXISTS idx_onvio_fila_status
                ON onvio_fila (status, data_criacao);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_onvio_fila_parcela_ativa
                ON onvio_fila (parcela_id)
                WHERE status IN ('AGUARDANDO', 'PROCESSANDO');
            """
        )
        _ensure_column(conn, "psn_disponibilidades", "valor", "REAL")


def _ensure_column(conn, table_name, column_name, definition):
    columns = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_app(app):
    app.teardown_appcontext(close_db)
