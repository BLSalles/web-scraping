import re
import unicodedata
from urllib.parse import urlparse

from .models import Lead

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
EMAIL_LIXO = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", "sentry", "wixpress", "example.", "seudominio", "email.com")
DOMINIOS_IGNORADOS = ("google.", "facebook.com", "instagram.com", "wa.me", "whatsapp.com", "linkedin.com", "youtube.com", "linktr.ee")


def so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def sem_acento(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


def telefone(valor):
    d = so_digitos(valor)
    if d.startswith("0") and len(d) in (11, 12):
        d = d[1:]
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11) or d[0] == "0":
        return ""
    return "55" + d


def telefone_formatado(valor):
    d = telefone(valor)
    if not d:
        return ""
    ddd, num = d[2:4], d[4:]
    return f"({ddd}) {num[:-4]}-{num[-4:]}"


def eh_celular(valor):
    d = telefone(valor)
    return len(d) == 13 and d[4] == "9"


def email(valor):
    valor = (valor or "").strip().lower().strip(".")
    if not EMAIL_RE.fullmatch(valor) or any(x in valor for x in EMAIL_LIXO):
        return ""
    return valor


def dominio(url):
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).netloc.lower().split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    if any(d in host for d in DOMINIOS_IGNORADOS):
        return ""
    return host


def cnpj(valor):
    d = so_digitos(valor)
    return d if len(d) == 14 else ""


def chaves(lead: Lead):
    out = []
    if lead.cnpj:
        out.append("cnpj:" + lead.cnpj)
    if dominio(lead.site):
        out.append("dom:" + dominio(lead.site))
    if lead.telefone:
        out.append("tel:" + lead.telefone)
    nome = sem_acento(lead.nome or lead.razao_social)
    if nome and lead.cidade:
        out.append("nome:" + re.sub(r"[^a-z0-9]", "", nome) + "|" + sem_acento(lead.cidade))
    return out


def limpar(lead: Lead) -> Lead:
    lead.telefone = telefone(lead.telefone)
    lead.whatsapp = telefone(lead.whatsapp)
    if not lead.whatsapp and eh_celular(lead.telefone):
        lead.whatsapp = lead.telefone
    lead.email = email(lead.email)
    lead.cnpj = cnpj(lead.cnpj)
    lead.uf = (lead.uf or "").upper()[:2]
    lead.cep = so_digitos(lead.cep)[:8]
    lead.telefones_extras = sorted({t for t in map(telefone, lead.telefones_extras) if t and t != lead.telefone})
    lead.emails_extras = sorted({e for e in map(email, lead.emails_extras) if e and e != lead.email})
    if not lead.email and lead.emails_extras:
        lead.email = lead.emails_extras.pop(0)
    if not lead.telefone and lead.telefones_extras:
        lead.telefone = lead.telefones_extras.pop(0)
    return lead


def mesclar(base: Lead, novo: Lead) -> Lead:
    for campo, valor in novo.to_dict().items():
        if campo in ("fontes", "telefones_extras", "emails_extras"):
            setattr(base, campo, sorted(set(getattr(base, campo)) | set(valor)))
        elif valor not in ("", None) and getattr(base, campo) in ("", None):
            setattr(base, campo, valor)
    return limpar(base)


def deduplicar(leads):
    unicos: list[Lead] = []
    indice: dict[str, int] = {}
    for lead in map(limpar, leads):
        pos = next((indice[k] for k in chaves(lead) if k in indice), None)
        if pos is None:
            unicos.append(lead)
            pos = len(unicos) - 1
        else:
            unicos[pos] = mesclar(unicos[pos], lead)
        for k in chaves(unicos[pos]):
            indice[k] = pos
    return unicos
