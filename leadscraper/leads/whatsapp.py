import re
from urllib.parse import quote

VARIAVEIS = ("nome", "razao_social", "cidade", "bairro", "uf", "site", "nota")


def primeiro_nome_empresa(nome):
    nome = re.sub(r"\b(ltda|me|eireli|epp|s/?a|ss)\b\.?", "", nome or "", flags=re.I)
    return re.sub(r"\s{2,}", " ", nome).strip(" -.,")


def montar_texto(modelo, lead):
    valores = {k: (lead.get(k) or "") for k in VARIAVEIS}
    valores["nome"] = primeiro_nome_empresa(valores["nome"] or valores["razao_social"]) or "equipe"
    texto = modelo
    for k, v in valores.items():
        texto = texto.replace("{" + k + "}", str(v))
    return re.sub(r"\{[a-z_]+\}", "", texto).strip()


def link(numero, texto, web=False):
    base = "https://web.whatsapp.com/send?phone=" if web else "https://wa.me/"
    sep = "&text=" if web else "?text="
    return f"{base}{numero}{sep}{quote(texto)}"
