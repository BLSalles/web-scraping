import re
from urllib.parse import urljoin, urlparse, unquote

from bs4 import BeautifulSoup

from .. import http
from ..models import Lead
from ..normalize import EMAIL_RE, dominio, email, telefone

NOME = "Sites das empresas"
PAGINAS_CONTATO = ("contato", "contact", "fale-conosco", "faleconosco", "atendimento", "sobre", "quem-somos")
TEL_RE = re.compile(r"(?:\+?55\s?)?\(?\b[1-9]{2}\)?[\s.-]?9?\s?\d{4}[\s.-]?\d{4}\b")
CNPJ_RE = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")


def _url(site):
    site = site.strip()
    return site if site.startswith("http") else "https://" + site


def extrair(site, max_paginas=4):
    base = _url(site)
    achado = {"emails": set(), "telefones": set(), "whatsapp": "", "instagram": "", "facebook": "", "linkedin": "", "cnpj": "", "titulo": ""}
    fila, vistos = [base], set()

    while fila and len(vistos) < max_paginas:
        url = fila.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        r = http.get(url)
        if r is None or "html" not in r.headers.get("content-type", ""):
            continue
        soup = BeautifulSoup(r.text, "lxml")
        if not achado["titulo"] and soup.title:
            achado["titulo"] = soup.title.get_text(strip=True)[:120]
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        texto = soup.get_text(" ", strip=True)

        achado["emails"] |= {e for e in map(email, EMAIL_RE.findall(texto)) if e}
        achado["telefones"] |= {t for t in map(telefone, TEL_RE.findall(texto)) if t}
        if not achado["cnpj"]:
            m = CNPJ_RE.search(texto)
            achado["cnpj"] = re.sub(r"\D", "", m.group()) if m else ""

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            low = href.lower()
            if low.startswith("mailto:"):
                e = email(unquote(href[7:].split("?")[0]))
                if e:
                    achado["emails"].add(e)
            elif low.startswith("tel:"):
                t = telefone(href[4:])
                if t:
                    achado["telefones"].add(t)
            elif "wa.me/" in low or "api.whatsapp.com" in low or "whatsapp://" in low:
                m = re.search(r"(?:wa\.me/|phone=)(\+?\d{10,13})", href)
                if m and not achado["whatsapp"]:
                    achado["whatsapp"] = telefone(m.group(1))
            elif "instagram.com/" in low and not achado["instagram"]:
                achado["instagram"] = href.split("?")[0]
            elif "facebook.com/" in low and not achado["facebook"] and "sharer" not in low:
                achado["facebook"] = href.split("?")[0]
            elif "linkedin.com/company" in low and not achado["linkedin"]:
                achado["linkedin"] = href.split("?")[0]
            else:
                alvo = urljoin(url, href).split("#")[0]
                if urlparse(alvo).netloc == urlparse(base).netloc and any(k in alvo.lower() for k in PAGINAS_CONTATO):
                    if alvo not in vistos and alvo not in fila:
                        fila.append(alvo)

    dom = dominio(base)
    emails = sorted(achado["emails"], key=lambda e: (not e.endswith("@" + dom), e))
    achado["emails"] = emails
    achado["telefones"] = sorted(achado["telefones"])
    return achado


def enriquecer(lead: Lead):
    if not lead.site:
        return lead
    d = extrair(lead.site)
    lead.emails_extras = sorted(set(lead.emails_extras) | set(d["emails"]))
    lead.telefones_extras = sorted(set(lead.telefones_extras) | set(d["telefones"]))
    for campo in ("whatsapp", "instagram", "facebook", "linkedin", "cnpj"):
        if d[campo] and not getattr(lead, campo):
            setattr(lead, campo, d[campo])
    if "site" not in lead.fontes:
        lead.fontes = sorted(set(lead.fontes) | {"site"})
    return lead


def buscar(p, log):
    urls = [u.strip() for u in re.split(r"[\n,;]+", p.get("urls") or "") if u.strip()]
    if not urls:
        log("Fonte 'Sites': nenhuma URL informada (os sites encontradas nas outras fontes são varridos no enriquecimento).")
        return
    for url in urls[: p["limite"]]:
        log(f"varrendo {url}")
        d = extrair(url)
        yield Lead(
            nome=d["titulo"] or dominio(url),
            site=_url(url),
            cnpj=d["cnpj"],
            whatsapp=d["whatsapp"],
            instagram=d["instagram"],
            facebook=d["facebook"],
            linkedin=d["linkedin"],
            emails_extras=d["emails"],
            telefones_extras=d["telefones"],
            cidade=p.get("cidade", ""),
            uf=p.get("uf", ""),
            fontes=["site"],
        )
