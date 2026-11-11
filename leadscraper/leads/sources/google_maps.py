import glob
import json
import math
import os
import subprocess
import sys
import time

import requests

from .. import KIT_API_KEY, KIT_DIR, KIT_URL, SEM_NAVEGADOR, USER_AGENT
from ..models import Lead
from ..segmentos import expandir

NOME = "Google Maps"
POR_PAGINA = 20
TETO_BUSCA = 120
MAX_GRADE = 4
_processo = None


def _headers():
    return {"X-API-Key": KIT_API_KEY} if KIT_API_KEY else {}


def _api(metodo, caminho, **kw):
    return requests.request(metodo, KIT_URL + caminho, headers=_headers(), timeout=kw.pop("timeout", 30), **kw)


def _no_ar():
    try:
        return _api("GET", "/api/v1/jobs", timeout=3).ok
    except requests.RequestException:
        return False


def _chrome():
    if os.getenv("CHROME"):
        return os.environ["CHROME"]
    for c in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
              *glob.glob("/ms-playwright/chromium-*/chrome-linux*/chrome")]:
        if os.path.exists(c):
            return c
    return ""


def garantir_motor(log):
    global _processo
    if _no_ar():
        return True
    serve = os.path.join(KIT_DIR, "engine", "serve.py")
    if not os.path.exists(serve):
        log(f"Motor do Google Maps não encontrado em {KIT_DIR}. Clone o google-maps-scraper-kit ou ajuste KIT_DIR.")
        return False
    if _processo is None or _processo.poll() is not None:
        porta = KIT_URL.rsplit(":", 1)[-1].strip("/")
        env = dict(os.environ, SCRAPER_PORT=porta, SCRAPER_NO_UPDATE_CHECK="1")
        if _chrome():
            env["CHROME"] = _chrome()
        log("iniciando o motor do Google Maps...")
        _processo = subprocess.Popen([sys.executable, serve, "--port", porta], cwd=KIT_DIR, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if _no_ar():
            return True
        if _processo.poll() is not None:
            break
        time.sleep(1)
    log("O motor do Google Maps não subiu.")
    return False


def _geocodificar(cidade, uf):
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", timeout=20, headers={"User-Agent": USER_AGENT},
                         params={"format": "json", "limit": 1, "countrycodes": "br", "q": f"{cidade}, {uf}".strip(", ")})
        hits = r.json() if r.ok else []
        return [float(x) for x in hits[0]["boundingbox"]] if hits else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def _grade(bbox, n):
    s, nn, w, e = bbox
    dlat, dlon = (nn - s) / n, (e - w) / n
    celulas = []
    for i in range(n):
        for j in range(n):
            lat, lon = s + (i + 0.5) * dlat, w + (j + 0.5) * dlon
            largura = max(1.0, dlon * 111195 * math.cos(math.radians(lat)))
            zoom = round(math.log2(156543.03 * math.cos(math.radians(lat)) * 1000 / largura))
            celulas.append({"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": min(17, max(11, zoom))})
    return celulas


def _rodar_job(corpo, log):
    r = _api("POST", "/api/v1/jobs", json=corpo)
    if not r.ok:
        log(f"Google Maps recusou a busca ({r.status_code}): {r.text[:200]}")
        return []
    jid = r.json()["id"]
    limite_espera = time.time() + corpo["max_time"] + 180
    ultimo = None
    try:
        while time.time() < limite_espera:
            time.sleep(4)
            j = _api("GET", f"/api/v1/jobs/{jid}").json()
            prog = j.get("Progress") or {}
            msg = f"  Google Maps: {prog.get('places', 0)} lugares ({prog.get('stage', '')})"
            if msg != ultimo and prog.get("stage") not in (None, "queued"):
                log(msg)
                ultimo = msg
            if j.get("Status") in ("ok", "failed"):
                if j.get("Error"):
                    log(f"  aviso do Google Maps: {j['Error'][:200]}")
                break
        d = _api("GET", f"/api/v1/jobs/{jid}/download", params={"format": "json"}, timeout=60)
        return d.json() if d.ok and d.content.strip() else []
    finally:
        try:
            _api("DELETE", f"/api/v1/jobs/{jid}")
        except requests.RequestException:
            pass


def _para_lead(r, p):
    emails = [e.strip() for e in (r.get("emails") or "").split(",") if e.strip()]
    try:
        comp = json.loads(r.get("complete_address") or "{}")
    except ValueError:
        comp = {}
    if not isinstance(comp, dict):
        comp = {}
    try:
        nota = float(r.get("review_rating") or 0) or None
    except ValueError:
        nota = None
    try:
        avaliacoes = int(float(r.get("review_count") or 0)) or None
    except ValueError:
        avaliacoes = None
    return Lead(
        nome=r.get("title", ""),
        telefone=r.get("phone", ""),
        email=emails[0] if emails else "",
        emails_extras=emails[1:],
        site=r.get("website", ""),
        instagram=r.get("instagram", ""),
        facebook=r.get("facebook", ""),
        linkedin=r.get("linkedin", ""),
        endereco=r.get("address", ""),
        bairro=comp.get("borough", ""),
        cidade=comp.get("city") or p.get("cidade", ""),
        uf=p.get("uf", "") or comp.get("state", "")[:2],
        cep=comp.get("postal_code", ""),
        nota=nota,
        avaliacoes=avaliacoes,
        maps_url=r.get("link", ""),
        fontes=["google_maps"],
    )


def buscar(p, log):
    if SEM_NAVEGADOR:
        log("Google Maps desligado neste servidor (SEM_NAVEGADOR=1).")
        return
    if not garantir_motor(log):
        return
    local = " ".join(x for x in (p.get("cidade"), p.get("uf")) if x)
    termos = expandir(p["nicho"])
    palavras = [f"{t} em {local}".strip() if local else t for t in termos]
    por_termo = max(1, math.ceil(p["limite"] / len(termos)))
    depth = min(math.ceil(por_termo / POR_PAGINA), TETO_BUSCA // POR_PAGINA)
    corpo = {"name": f"leadscraper {p['nicho']} {local}", "keywords": palavras, "lang": "pt", "country": "br",
             "depth": depth, "email": True, "socials": True, "max_time": 120 + 40 * depth * len(palavras)}

    celulas = [{}]
    if por_termo > TETO_BUSCA and p.get("cidade"):
        bbox = _geocodificar(p["cidade"], p.get("uf", ""))
        if bbox:
            n = min(MAX_GRADE, math.ceil(math.sqrt(por_termo / 100)))
            celulas = _grade(bbox, n)
            log(f"Google Maps: cidade dividida em {n}x{n} áreas para passar do limite de ~120 por busca")

    vistos, total = set(), 0
    for i, cel in enumerate(celulas, 1):
        if len(celulas) > 1:
            log(f"  área {i}/{len(celulas)}")
        log(f"Google Maps: {', '.join(palavras[:3])}{'...' if len(palavras) > 3 else ''}")
        try:
            linhas = _rodar_job({**corpo, **cel}, log)
        except requests.RequestException as e:
            log(f"Google Maps falhou: {e.__class__.__name__}")
            return
        for r in linhas:
            chave = r.get("place_id") or r.get("data_id") or r.get("link") or r.get("title")
            if chave in vistos:
                continue
            vistos.add(chave)
            yield _para_lead(r, p)
            total += 1
            if total >= p["limite"]:
                return
