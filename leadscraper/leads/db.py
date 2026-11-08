import json
import os
import sqlite3
from contextlib import contextmanager

from . import DB_PATH
from .models import Lead
from .normalize import chaves, mesclar

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dados TEXT NOT NULL,
    nome TEXT, cidade TEXT, uf TEXT,
    status TEXT DEFAULT 'novo',
    busca TEXT,
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    contatado_em TEXT
);
CREATE TABLE IF NOT EXISTS lead_chaves (chave TEXT PRIMARY KEY, lead_id INTEGER);
CREATE TABLE IF NOT EXISTS modelos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    texto TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS optout (telefone TEXT PRIMARY KEY, criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
"""

STATUS = ("novo", "contatado", "respondeu", "cliente", "descartado")


@contextmanager
def conexao():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _lead(row):
    lead = Lead(**json.loads(row["dados"]))
    d = lead.to_dict()
    d.update(id=row["id"], status=row["status"], busca=row["busca"], criado_em=row["criado_em"], contatado_em=row["contatado_em"])
    return d


def salvar(leads, busca=""):
    novos = atualizados = 0
    with conexao() as con:
        for lead in leads:
            ks = chaves(lead)
            row = None
            for k in ks:
                hit = con.execute("SELECT l.* FROM lead_chaves c JOIN leads l ON l.id = c.lead_id WHERE c.chave = ?", (k,)).fetchone()
                if hit:
                    row = hit
                    break
            if row:
                lead = mesclar(Lead(**json.loads(row["dados"])), lead)
                con.execute("UPDATE leads SET dados=?, nome=?, cidade=?, uf=? WHERE id=?",
                            (json.dumps(lead.to_dict(), ensure_ascii=False), lead.nome or lead.razao_social, lead.cidade, lead.uf, row["id"]))
                lead_id = row["id"]
                atualizados += 1
            else:
                cur = con.execute("INSERT INTO leads (dados, nome, cidade, uf, busca) VALUES (?,?,?,?,?)",
                                  (json.dumps(lead.to_dict(), ensure_ascii=False), lead.nome or lead.razao_social, lead.cidade, lead.uf, busca))
                lead_id = cur.lastrowid
                novos += 1
            for k in chaves(lead):
                con.execute("INSERT OR REPLACE INTO lead_chaves VALUES (?,?)", (k, lead_id))
    return novos, atualizados


def listar(status=None, busca=None, texto=None, so_whatsapp=False, limite=5000):
    sql, args = "SELECT * FROM leads WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if busca:
        sql += " AND busca = ?"
        args.append(busca)
    if texto:
        sql += " AND (dados LIKE ? )"
        args.append(f"%{texto}%")
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limite)
    with conexao() as con:
        bloqueados = {r[0] for r in con.execute("SELECT telefone FROM optout")}
        out = [_lead(r) for r in con.execute(sql, args)]
    for d in out:
        d["optout"] = d["whatsapp"] in bloqueados or d["telefone"] in bloqueados
    if so_whatsapp:
        out = [d for d in out if d["whatsapp"] and not d["optout"]]
    return out


def obter(lead_id):
    with conexao() as con:
        row = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    return _lead(row) if row else None


def mudar_status(lead_id, status):
    if status not in STATUS:
        raise ValueError(status)
    with conexao() as con:
        con.execute("UPDATE leads SET status=?, contatado_em=CASE WHEN ?='contatado' THEN CURRENT_TIMESTAMP ELSE contatado_em END WHERE id=?",
                    (status, status, lead_id))


def bloquear(telefone):
    with conexao() as con:
        con.execute("INSERT OR IGNORE INTO optout (telefone) VALUES (?)", (telefone,))


def excluir(lead_id):
    with conexao() as con:
        con.execute("DELETE FROM lead_chaves WHERE lead_id=?", (lead_id,))
        con.execute("DELETE FROM leads WHERE id=?", (lead_id,))


def contatados_hoje():
    with conexao() as con:
        return con.execute("SELECT COUNT(*) FROM leads WHERE date(contatado_em, 'localtime') = date('now', 'localtime')").fetchone()[0]


def buscas():
    with conexao() as con:
        return [r[0] for r in con.execute("SELECT DISTINCT busca FROM leads WHERE busca != '' ORDER BY busca")]


def contagem():
    with conexao() as con:
        return {r[0]: r[1] for r in con.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")}


def modelos():
    with conexao() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM modelos ORDER BY id")]
        if not rows:
            con.execute("INSERT INTO modelos (nome, texto) VALUES (?,?)", (
                "Primeiro contato - energia solar",
                "Olá, tudo bem? Falo com a {nome}?\n\nTrabalho com energia solar aqui na região de {cidade} e tenho ajudado empresas "
                "a reduzir bastante a conta de luz, com o sistema se pagando com a própria economia.\n\n"
                "Posso fazer uma simulação gratuita pra vocês? Só preciso de uma foto da última conta de energia.\n\n"
                "Se preferir não receber mensagens, é só responder SAIR.",
            ))
            rows = [dict(r) for r in con.execute("SELECT * FROM modelos ORDER BY id")]
    return rows


def salvar_modelo(nome, texto, modelo_id=None):
    with conexao() as con:
        if modelo_id:
            con.execute("UPDATE modelos SET nome=?, texto=? WHERE id=?", (nome, texto, modelo_id))
        else:
            con.execute("INSERT INTO modelos (nome, texto) VALUES (?,?)", (nome, texto))
