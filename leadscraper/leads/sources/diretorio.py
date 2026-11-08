import os
from urllib.parse import quote_plus, urljoin

import yaml
from bs4 import BeautifulSoup

from .. import http
from ..models import Lead

NOME = "Diretórios / sites de listagem"
CONFIG = os.path.join(os.path.dirname(__file__), "..", "..", "diretorios.yaml")


def carregar():
    if not os.path.exists(CONFIG):
        return {}
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _valor(item, regra, url_base):
    if not regra:
        return ""
    sel, _, attr = regra.partition("@")
    el = item.select_one(sel) if sel else item
    if el is None:
        return ""
    if attr:
        v = el.get(attr, "")
        return urljoin(url_base, v) if attr == "href" else v
    return el.get_text(" ", strip=True)


def buscar(p, log):
    configs = carregar()
    escolhidos = p.get("diretorios") or list(configs)
    if not escolhidos:
        log("Nenhum diretório configurado em diretorios.yaml")
        return
    total = 0
    for nome in escolhidos:
        cfg = configs.get(nome)
        if not cfg:
            continue
        url = cfg["url"].format(nicho=quote_plus(p["nicho"]), cidade=quote_plus(p.get("cidade", "")),
                                uf=(p.get("uf") or "").lower(), nicho_slug=_slug(p["nicho"]), cidade_slug=_slug(p.get("cidade", "")))
        paginas = 0
        while url and paginas < cfg.get("max_paginas", 5) and total < p["limite"]:
            log(f"[{nome}] {url}")
            r = http.get(url, respeitar_robots=cfg.get("respeitar_robots", True))
            if r is None:
                log(f"[{nome}] página bloqueada pelo robots.txt ou indisponível")
                break
            soup = BeautifulSoup(r.text, "lxml")
            itens = soup.select(cfg["item"])
            if not itens:
                log(f"[{nome}] nenhum item com o seletor '{cfg['item']}'")
                break
            for item in itens:
                campos = {k: _valor(item, v, url) for k, v in cfg.get("campos", {}).items()}
                if not campos.get("nome"):
                    continue
                yield Lead(
                    nome=campos.get("nome", ""),
                    telefone=campos.get("telefone", ""),
                    email=campos.get("email", ""),
                    site=campos.get("site", ""),
                    endereco=campos.get("endereco", ""),
                    bairro=campos.get("bairro", ""),
                    cidade=campos.get("cidade") or p.get("cidade", ""),
                    uf=campos.get("uf") or p.get("uf", ""),
                    fontes=[f"diretorio:{nome}"],
                )
                total += 1
                if total >= p["limite"]:
                    return
            prox = soup.select_one(cfg["proxima"]) if cfg.get("proxima") else None
            url = urljoin(url, prox["href"]) if prox and prox.get("href") else None
            paginas += 1


def _slug(t):
    from ..normalize import sem_acento
    import re
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(t)).strip("-")
