import re

import requests

from . import USER_AGENT
from .models import Lead

API = "https://api.opencnpj.org/{cnpj}"


def _achar(d, *chaves):
    if isinstance(d, dict):
        for k in chaves:
            if d.get(k) not in (None, "", []):
                return d[k]
        for v in d.values():
            achado = _achar(v, *chaves)
            if achado not in (None, "", []):
                return achado
    return None


def _telefones(valor):
    out = []
    for t in valor or []:
        if isinstance(t, dict):
            if t.get("is_fax") or t.get("isFax"):
                continue
            out.append(f"{t.get('ddd', '')}{t.get('numero', '')}")
        else:
            out.append(str(t))
    return out


def consultar(cnpj):
    try:
        r = requests.get(API.format(cnpj=cnpj), headers={"User-Agent": USER_AGENT}, timeout=15)
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def enriquecer(lead: Lead):
    if not lead.cnpj or (lead.telefone and lead.email and lead.razao_social):
        return lead
    d = consultar(lead.cnpj)
    if not d:
        return lead
    lead.razao_social = lead.razao_social or (_achar(d, "razao_social", "razaoSocial") or "")
    lead.nome = lead.nome or (_achar(d, "nome_fantasia", "nomeFantasia") or lead.razao_social)
    email = _achar(d, "email")
    if email and "*" not in str(email):
        lead.emails_extras = sorted(set(lead.emails_extras) | {str(email)})
    tels = [t for t in _telefones(_achar(d, "telefones")) if not re.fullmatch(r"\d{2}\d0{7}", t)]
    lead.telefones_extras = sorted(set(lead.telefones_extras) | set(tels))
    cnae = _achar(d, "cnae_principal", "cnaePrincipal", "cnae_fiscal")
    lead.cnae = lead.cnae or str((cnae.get("codigo") if isinstance(cnae, dict) else cnae) or "")
    lead.porte = lead.porte or str(_achar(d, "porte_empresa", "porte") or "")
    lead.fontes = sorted(set(lead.fontes) | {"opencnpj"})
    return lead
