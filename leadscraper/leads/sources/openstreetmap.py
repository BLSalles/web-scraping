import re

import requests

from .. import USER_AGENT
from ..models import Lead
from ..normalize import sem_acento
from ..segmentos import expandir

NOME = "OpenStreetMap (grátis)"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CHAVES_POI = "shop|amenity|office|craft|healthcare|tourism|leisure"

MAPA = [
    (("dentist", "odonto"), ['amenity"="dentist']),
    (("clinica", "medic", "consultorio"), ['amenity"="clinic', 'amenity"="doctors']),
    (("veterin",), ['amenity"="veterinary']),
    (("pet", "petshop"), ['shop"="pet', 'amenity"="veterinary']),
    (("academia", "crossfit", "pilates"), ['leisure"="fitness_centre']),
    (("restaurante",), ['amenity"="restaurant']),
    (("lanchonete", "hamburgu"), ['amenity"="fast_food']),
    (("pizzaria",), ['cuisine"="pizza']),
    (("padaria",), ['shop"="bakery']),
    (("farmacia", "drogaria"), ['amenity"="pharmacy']),
    (("contab", "contador"), ['office"="accountant']),
    (("advoca", "advogad"), ['office"="lawyer']),
    (("imobiliaria",), ['office"="estate_agent']),
    (("salao", "cabeleireir", "barbearia"), ['shop"="hairdresser']),
    (("estetica", "beleza"), ['shop"="beauty']),
    (("oficina", "mecanica", "auto center"), ['shop"="car_repair']),
    (("mercado", "supermercado", "minimercado"), ['shop"="supermarket', 'shop"="convenience']),
    (("hotel", "pousada"), ['tourism"="hotel', 'tourism"="guest_house']),
    (("auto escola", "autoescola"), ['amenity"="driving_school']),
    (("escola", "colegio"), ['amenity"="school']),
    (("otica",), ['shop"="optician']),
    (("roupa", "moda"), ['shop"="clothes']),
    (("construcao",), ['shop"="hardware', 'shop"="doityourself']),
    (("cafe", "cafeteria"), ['amenity"="cafe']),
    (("bar",), ['amenity"="bar', 'amenity"="pub']),
]


def tags_para(nicho):
    n = sem_acento(nicho)
    out = []
    for termos, tags in MAPA:
        if any(re.search(rf"\b{t}\b" if len(t) <= 4 else rf"\b{t}", n) for t in termos):
            out += tags
    return list(dict.fromkeys(out))


def montar_query(nicho, cidade, limite):
    termo = re.sub(r'["\\]', "", nicho).strip()
    filtros = [f'nwr(area.a)["{t}"]["name"];' for t in tags_para(nicho)]
    filtros += [f'nwr(area.a)["{k}"]["name"~"{termo}",i];' for k in CHAVES_POI.split("|")]
    return (
        "[out:json][timeout:50];\n"
        f'area["boundary"="administrative"]["admin_level"="8"]["name"="{cidade}"]->.a;\n'
        "(\n  " + "\n  ".join(filtros) + "\n);\n"
        f"out center tags {limite};"
    )


def _tag(t, *nomes):
    for n in nomes:
        if t.get(n):
            return t[n].split(";")[0].strip()
    return ""


def para_lead(el, p):
    t = el.get("tags", {})
    endereco = ", ".join(x for x in (_tag(t, "addr:street"), _tag(t, "addr:housenumber")) if x)
    return Lead(
        nome=t.get("name", ""),
        telefone=_tag(t, "phone", "contact:phone"),
        whatsapp=_tag(t, "contact:whatsapp", "whatsapp", "mobile", "contact:mobile"),
        email=_tag(t, "email", "contact:email"),
        site=_tag(t, "website", "contact:website", "url"),
        instagram=_tag(t, "contact:instagram"),
        facebook=_tag(t, "contact:facebook"),
        endereco=endereco,
        bairro=_tag(t, "addr:suburb", "addr:neighbourhood"),
        cidade=_tag(t, "addr:city") or p["cidade"],
        uf=p.get("uf", ""),
        cep=_tag(t, "addr:postcode"),
        cnpj=_tag(t, "ref:vatin", "ref:CNPJ"),
        maps_url=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        fontes=["openstreetmap"],
    )


def buscar(p, log):
    if not p.get("cidade"):
        log("OpenStreetMap precisa da cidade preenchida.")
        return
    termos = expandir(p["nicho"])
    for termo in termos:
        yield from _buscar_termo(dict(p, nicho=termo, limite=max(1, p["limite"] // len(termos))), log)


def _buscar_termo(p, log):
    query = montar_query(p["nicho"], p["cidade"], p["limite"])
    tags = tags_para(p["nicho"])
    log(f"OpenStreetMap: {p['nicho']} em {p['cidade']}" + (f" (categorias: {', '.join(x.replace(chr(34), '') for x in tags)})" if tags else " (busca pelo nome)"))
    dados = None
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=60)
            if r.ok:
                dados = r.json()
                break
            log(f"{url.split('/')[2]} respondeu {r.status_code}, tentando outro servidor...")
        except requests.RequestException as e:
            log(f"{url.split('/')[2]} falhou ({e.__class__.__name__}: {str(e)[:120]}), tentando outro servidor...")
    if dados is None:
        log("Nenhum servidor do OpenStreetMap respondeu. Tente de novo em alguns minutos.")
        return
    vistos = set()
    for el in dados.get("elements", []):
        nome = el.get("tags", {}).get("name")
        if not nome or (nome, el.get("id")) in vistos:
            continue
        vistos.add((nome, el.get("id")))
        yield para_lead(el, p)
