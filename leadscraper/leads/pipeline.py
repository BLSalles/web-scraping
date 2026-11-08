import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import db
from .normalize import deduplicar
from .sources import FONTES, websites

JOBS: dict[str, dict] = {}


def rodar(params, fontes, enriquecer_sites=True, log=print):
    coletados = []
    for chave in fontes:
        fonte = FONTES[chave]
        try:
            antes = len(coletados)
            coletados.extend(fonte.buscar(params, log))
            log(f"{fonte.NOME}: {len(coletados) - antes} registros")
        except Exception as e:
            log(f"{fonte.NOME} falhou: {e}")

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

    rotulo = f"{params['nicho']} - {params.get('cidade') or params.get('uf') or 'BR'} ({time.strftime('%d/%m %H:%M')})"
    novos, atualizados = db.salvar(leads, busca=rotulo)
    log(f"salvo: {novos} novos, {atualizados} já existiam e foram completados")
    return rotulo


def iniciar_job(params, fontes, enriquecer_sites=True):
    job_id = uuid.uuid4().hex[:8]
    job = {"id": job_id, "status": "rodando", "log": [], "busca": None}
    JOBS[job_id] = job

    def log(msg):
        job["log"].append(f"{time.strftime('%H:%M:%S')}  {msg}")

    def alvo():
        try:
            job["busca"] = rodar(params, fontes, enriquecer_sites, log)
            job["status"] = "concluido"
        except Exception as e:
            log(f"erro: {e}")
            job["status"] = "erro"

    threading.Thread(target=alvo, daemon=True).start()
    return job_id
