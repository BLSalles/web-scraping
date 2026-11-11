from flask import Flask, Response, jsonify, render_template, request

from leads import db, whatsapp
from leads.export import csv_bytes, xlsx_bytes
from leads.pipeline import JOBS, iniciar_job
import hmac
import os

app = Flask(__name__)
APP_USER = os.getenv("APP_USER", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


@app.before_request
def autenticar():
    if not APP_PASSWORD or request.path == "/saude":
        return None
    a = request.authorization
    if a and hmac.compare_digest(a.username or "", APP_USER) and hmac.compare_digest(a.password or "", APP_PASSWORD):
        return None
    return Response("Login necessário", 401, {"WWW-Authenticate": 'Basic realm="LeadScraper"'})


@app.get("/saude")
def saude():
    return "ok"


@app.get("/")
def index():
    return render_template(
        "index.html",
        status=db.STATUS,
    )


@app.post("/api/buscar")
def buscar():
    b = request.get_json()
    if not (b.get("nicho") or "").strip():
        return jsonify(erro="Informe o segmento"), 400
    params = {
        "nicho": b["nicho"].strip(),
        "cidade": (b.get("cidade") or "").strip(),
        "uf": (b.get("uf") or "").strip().upper(),
        "limite": max(1, min(int(b.get("limite") or 50), 2000)),
        "cnae": b.get("cnae", ""),
        "so_com_contato": bool(b.get("so_com_contato")),
        "so_whatsapp": bool(b.get("so_whatsapp")),
        "so_email": bool(b.get("so_email")),
        "nota_min": float(b.get("nota_min") or 0),
        "min_avaliacoes": int(b.get("min_avaliacoes") or 0),
        "aberta_desde": b.get("aberta_desde", ""),
        "porte": b.get("porte") or [],
    }
    return jsonify(job=iniciar_job(params))


@app.get("/api/job/<job_id>")
def job(job_id):
    j = JOBS.get(job_id)
    return (jsonify(j), 200) if j else (jsonify(erro="job não encontrado"), 404)


def _filtros():
    a = request.args
    return dict(status=a.get("status") or None, busca=a.get("busca") or None, texto=a.get("texto") or None)


@app.get("/api/leads")
def leads():
    return jsonify(leads=db.listar(**_filtros()), buscas=db.buscas(), contagem=db.contagem())


@app.post("/api/leads/<int:lead_id>/status")
def status(lead_id):
    db.mudar_status(lead_id, request.get_json()["status"])
    return jsonify(ok=True, hoje=db.contatados_hoje())


@app.post("/api/leads/<int:lead_id>/optout")
def optout(lead_id):
    lead = db.obter(lead_id)
    for tel in {lead["whatsapp"], lead["telefone"]} - {""}:
        db.bloquear(tel)
    db.mudar_status(lead_id, "descartado")
    return jsonify(ok=True)


@app.delete("/api/leads/<int:lead_id>")
def excluir(lead_id):
    db.excluir(lead_id)
    return jsonify(ok=True)


@app.get("/api/modelos")
def modelos():
    return jsonify(modelos=db.modelos(), variaveis=whatsapp.VARIAVEIS)


@app.post("/api/modelos")
def salvar_modelo():
    b = request.get_json()
    db.salvar_modelo(b["nome"], b["texto"], b.get("id"))
    return jsonify(modelos=db.modelos())


@app.get("/api/fila")
def fila():
    modelo = next((m for m in db.modelos() if str(m["id"]) == request.args.get("modelo")), db.modelos()[0])
    web = request.args.get("web") == "1"
    itens = []
    for d in db.listar(status="novo", busca=request.args.get("busca") or None, so_whatsapp=True):
        texto = whatsapp.montar_texto(modelo["texto"], d)
        itens.append({"id": d["id"], "nome": d["nome"], "cidade": d["cidade"], "whatsapp": d["whatsapp"],
                      "texto": texto, "link": whatsapp.link(d["whatsapp"], texto, web)})
    return jsonify(fila=itens, hoje=db.contatados_hoje())


@app.get("/exportar.<fmt>")
def exportar(fmt):
    dados = db.listar(**_filtros())
    if fmt == "xlsx":
        return Response(xlsx_bytes(dados), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=leads.xlsx"})
    return Response(csv_bytes(dados), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
