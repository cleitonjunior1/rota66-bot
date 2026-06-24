"""Camada de acesso ao SQLite.

Duas funcoes principais:
  1. Guardar a rota planejada (vinda da planilha Excel).
  2. Servir de cache offline para clima/postos/atracoes quando faltar sinal.
"""
import sqlite3
import json
import time
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Cria as tabelas se ainda nao existirem."""
    conn = get_conn()
    cur = conn.cursor()

    # Pontos planejados, vindos da planilha. 'ordem' define a sequencia da viagem.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS waypoints (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem     INTEGER,
            nome      TEXT,
            tipo      TEXT,
            cidade    TEXT,
            lat       REAL,
            lon       REAL,
            dicas     TEXT,
            link      TEXT,
            visitado  INTEGER DEFAULT 0
        )
    """)

    # Cache generico: chave -> json + timestamp. Usado para respostas offline.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            chave     TEXT PRIMARY KEY,
            valor     TEXT,
            criado_em REAL
        )
    """)

    # Estado por chat (ex.: ultima vez que respondemos a uma localizacao ao vivo).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS estado_chat (
            chat_id        INTEGER PRIMARY KEY,
            ultima_lat     REAL,
            ultima_lon     REAL,
            ultimo_aviso   REAL
        )
    """)

    conn.commit()
    conn.close()


# ----- Waypoints (rota planejada) -----

def limpar_waypoints():
    conn = get_conn()
    conn.execute("DELETE FROM waypoints")
    conn.commit()
    conn.close()


def inserir_waypoint(ordem, nome, tipo, cidade, lat, lon, dicas, link):
    conn = get_conn()
    conn.execute(
        "INSERT INTO waypoints (ordem, nome, tipo, cidade, lat, lon, dicas, link) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ordem, nome, tipo, cidade, lat, lon, dicas, link),
    )
    conn.commit()
    conn.close()


def listar_waypoints():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM waypoints ORDER BY ordem").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_visitado(waypoint_id):
    conn = get_conn()
    conn.execute("UPDATE waypoints SET visitado = 1 WHERE id = ?", (waypoint_id,))
    conn.commit()
    conn.close()


# ----- Cache offline -----

def salvar_cache(chave, valor_dict):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cache (chave, valor, criado_em) VALUES (?,?,?)",
        (chave, json.dumps(valor_dict), time.time()),
    )
    conn.commit()
    conn.close()


def ler_cache(chave, validade_segundos=86400):
    """Retorna o valor em cache se existir e nao estiver vencido (padrao: 24h)."""
    conn = get_conn()
    row = conn.execute("SELECT valor, criado_em FROM cache WHERE chave = ?", (chave,)).fetchone()
    conn.close()
    if not row:
        return None
    if time.time() - row["criado_em"] > validade_segundos:
        return None
    return json.loads(row["valor"])


# ----- Estado do chat -----

def get_estado(chat_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM estado_chat WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_estado(chat_id, lat, lon, ultimo_aviso):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO estado_chat (chat_id, ultima_lat, ultima_lon, ultimo_aviso) VALUES (?,?,?,?)",
        (chat_id, lat, lon, ultimo_aviso),
    )
    conn.commit()
    conn.close()
