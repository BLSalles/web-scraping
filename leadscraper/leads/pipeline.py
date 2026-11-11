import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import db, opencnpj
from .normalize import deduplicar
from .sources import FONTES, cnpj, diretorio, websites

JOBS: dict[str, dict] = {}


def fontes_automaticas():
    fontes = ["google_maps", "openstreetmap"]
    if cnpj.instalar_base(lambda *_: None):
        fontes.append("cnpj")
    if any(not n.startswith("exemplo") for n in diretorio.carregar()):
        fontes.append("diretorios")
    return fontes


def _coletar(chave, params, log):
    fonte = FONTES[chave]
    try:
        achados = list(fonte.buscar(params, log))
        log(f"{fonte.NOME}: {len(achados)} registros")
        return achados
    except Exception as e:
        log(f"{fonte.NOME} falhou: {e}")
        return []


def _pontos(l):
    return (bool(l.whatsapp) * 4 + bool(l.email) * 2 + bool(l.telefone) * 2 + len(l.fontes), l.avaliacoes or 0)


def filtrar(leads, params):
    if params.get("so_com_contato"):
        leads = [l for l in leads if l.telefone or l.whatsapp or l.email]
    if params.get("so_whatsapp"):
        leads = [l for l in leads if l.whatsapp]
    if params.get("so_email"):
        leads = [l for l in leads if l.email]
    if params.get("nota_min"):
        leads = [l for l in leads if l.nota is None or l.nota >= params["nota_min"]]
    if params.get("min_avaliacoes"):
        leads = [l for l in leads if l.avaliacoes is None or l.avaliacoes >= params["min_avaliacoes"]]
    return sorted(leads, key=_pontos, reverse=True)[: params["limite"]]


def rodar(params, fontes=None, enriquecer_sites=True, log=print, usar_opencnpj=True):
    fontes = fontes or fontes_automaticas()
    log("buscando em: " + ", ".join(FONTES[f].NOME for f in fontes))
    coletados = []
    with ThreadPoolExecutor(max_workers=len(fontes)) as ex:
        for achados in ex.map(lambda f: _coletar(f, params, log), fontes):
            coletados.extend(achados)

    leads = deduplicar(coletados)
    log(f"{len(leads)} leads únicos após juntar as fontes")

    if enriquecer_sites:
        com_site = [l for l in leads if l.site and "site" not in l.fontes]
        if com_site:
            log(f"varrendo {len(com_site)} sites atrás de e-mail, WhatsApp e redes...")
            with ThreadPoolExecutor(max_workers=6) as ex:
                for i, _ in enumerate(ex.map(websites.enriquecer, com_site), 1):
                    if i % 10 == 0:
                        log(f"  {i}/{len(com_site)} sites")
            leads = deduplicar(leads)

    if usar_opencnpj:
        com_cnpj = [l for l in leads if l.cnpj and not (l.telefone and l.email and l.razao_social)]
        if com_cnpj:
            log(f"completando {len(com_cnpj)} leads pelo CNPJ (OpenCNPJ)...")
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(opencnpj.enriquecer, com_cnpj))
            leads = deduplicar(leads)

    antes = len(leads)
    leads = filtrar(leads, params)
    if len(leads) < antes:
        log(f"{len(leads)} leads depois dos filtros (de {antes})")

    rotulo = f"{params['nicho']} - {params.get('cidade') or params.get('uf') or 'BR'} ({time.strftime('%d/%m %H:%M')})"
    novos, atualizados = db.salvar(leads, busca=rotulo)
    log(f"salvo: {novos} novos, {atualizados} já existiam e foram completados")
    return rotulo


def iniciar_job(params, fontes=None, enriquecer_sites=True, usar_opencnpj=True):
    job_id = uuid.uuid4().hex[:8]
    job = {"id": job_id, "status": "rodando", "log": [], "busca": None}
    JOBS[job_id] = job

    def log(msg):
        job["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")

    def alvo():
        try:
            job["busca"] = rodar(params, fontes, enriquecer_sites, log, usar_opencnpj)
            job["status"] = "concluido"
        except Exception as e:
            log(f"erro: {e}")
            job["status"] = "erro"

    threading.Thread(target=alvo, daemon=True).start()
    return job_id
