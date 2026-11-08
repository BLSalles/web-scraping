import re
import time
from urllib.parse import quote_plus

import requests

from .. import GOOGLE_PLACES_API_KEY
from ..models import Lead

NOME = "Google Maps"
API_URL = "https://places.googleapis.com/v1/places:searchText"
CAMPOS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents",
    "places.nationalPhoneNumber", "places.websiteUri", "places.rating", "places.userRatingCount",
    "places.googleMapsUri", "nextPageToken",
])


BLOQUEADOS = {"image", "media", "font"}
ARGS_LEVES = [
    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--single-process",
    "--disable-extensions", "--disable-background-networking", "--disable-component-update",
    "--mute-audio", "--renderer-process-limit=1", "--js-flags=--max-old-space-size=160",
]


def buscar(p, log):
    consulta = f"{p['nicho']} em {p['cidade']} {p.get('uf', '')}".strip()
    if GOOGLE_PLACES_API_KEY:
        log(f"Google Maps (API): {consulta}")
        yield from _via_api(consulta, p, log)
    else:
        log(f"Google Maps (navegador): {consulta}")
        yield from _via_navegador(consulta, p, log)


def _componente(comps, tipo):
    for c in comps or []:
        if tipo in c.get("types", []):
            return c.get("shortText") or c.get("longText", "")
    return ""


def _via_api(consulta, p, log):
    headers = {"X-Goog-Api-Key": GOOGLE_PLACES_API_KEY, "X-Goog-FieldMask": CAMPOS, "Content-Type": "application/json"}
    body = {"textQuery": consulta, "languageCode": "pt-BR", "regionCode": "BR", "pageSize": 20}
    total = 0
    while total < p["limite"]:
        r = requests.post(API_URL, json=body, headers=headers, timeout=20)
        if not r.ok:
            log(f"Places API erro {r.status_code}: {r.text[:200]}")
            return
        data = r.json()
        for pl in data.get("places", []):
            comps = pl.get("addressComponents")
            yield Lead(
                nome=pl.get("displayName", {}).get("text", ""),
                telefone=pl.get("nationalPhoneNumber", ""),
                site=pl.get("websiteUri", ""),
                endereco=pl.get("formattedAddress", ""),
                bairro=_componente(comps, "sublocality"),
                cidade=_componente(comps, "administrative_area_level_2") or p["cidade"],
                uf=_componente(comps, "administrative_area_level_1") or p.get("uf", ""),
                cep=_componente(comps, "postal_code"),
                nota=pl.get("rating"),
                avaliacoes=pl.get("userRatingCount"),
                maps_url=pl.get("googleMapsUri", ""),
                fontes=["google_maps"],
            )
            total += 1
            if total >= p["limite"]:
                return
        token = data.get("nextPageToken")
        if not token:
            return
        body["pageToken"] = token
        time.sleep(2)


def _via_navegador(consulta, p, log):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright não instalado. Rode: pip install playwright && playwright install chromium")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=p.get("headless", True), args=ARGS_LEVES)
        ctx = browser.new_context(locale="pt-BR", viewport={"width": 1000, "height": 700})
        ctx.route("**/*", lambda rota: rota.abort() if rota.request.resource_type in BLOQUEADOS else rota.continue_())
        page = ctx.new_page()
        page.goto(f"https://www.google.com/maps/search/{quote_plus(consulta)}?hl=pt-BR", wait_until="domcontentloaded")
        try:
            page.locator("form[action*='consent'] button").last.click(timeout=4000)
        except Exception:
            pass
        try:
            page.wait_for_selector("div[role='feed']", timeout=15000)
        except Exception:
            log("Lista de resultados não carregou (o Google pode ter mudado o layout ou pedido verificação).")
            browser.close()
            return

        feed = page.locator("div[role='feed']")
        links, parado = [], 0
        while len(links) < p["limite"] and parado < 4:
            antes = len(links)
            for a in page.locator("div[role='feed'] a[href*='/maps/place/']").all():
                href = a.get_attribute("href")
                if href and href not in links:
                    links.append(href)
            if "Você chegou ao final" in feed.inner_text() or "reached the end" in feed.inner_text():
                break
            feed.evaluate("el => el.scrollBy(0, el.scrollHeight)")
            page.wait_for_timeout(1800)
            parado = parado + 1 if len(links) == antes else 0

        log(f"{len(links[:p['limite']])} lugares encontrados, lendo detalhes...")
        for href in links[:p["limite"]]:
            try:
                page.goto(href, wait_until="domcontentloaded")
                page.wait_for_selector("h1", timeout=10000)
                page.wait_for_timeout(800)
                lead = Lead(nome=_txt(page, "h1"), maps_url=href, cidade=p["cidade"], uf=p.get("uf", ""), fontes=["google_maps"])
                lead.endereco = _attr_label(page, "button[data-item-id='address']")
                lead.telefone = _attr_label(page, "button[data-item-id^='phone:tel:']")
                site = page.locator("a[data-item-id='authority']")
                lead.site = site.first.get_attribute("href") if site.count() else ""
                nota = page.locator("div.F7nice span[aria-hidden='true']")
                if nota.count():
                    lead.nota = float(nota.first.inner_text().replace(",", "."))
                aval = page.locator("div.F7nice span[aria-label*='avalia']")
                if aval.count():
                    lead.avaliacoes = int(re.sub(r"\D", "", aval.first.get_attribute("aria-label")) or 0)
                cep = re.search(r"\d{5}-?\d{3}", lead.endereco)
                lead.cep = cep.group() if cep else ""
                yield lead
            except Exception as e:
                log(f"Falha lendo um lugar: {e.__class__.__name__}")
            page.wait_for_timeout(1200)
        browser.close()


def _txt(page, sel):
    el = page.locator(sel)
    return el.first.inner_text().strip() if el.count() else ""


def _attr_label(page, sel):
    el = page.locator(sel)
    if not el.count():
        return ""
    label = el.first.get_attribute("aria-label") or ""
    return label.split(":", 1)[-1].strip()
