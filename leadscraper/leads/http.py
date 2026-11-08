import time
import threading
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from . import REQUEST_DELAY, USER_AGENT

_lock = threading.Lock()
_ultimo_acesso: dict[str, float] = {}
_robots: dict[str, RobotFileParser | None] = {}

sessao = requests.Session()
sessao.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"})


def _aguardar(host):
    with _lock:
        espera = _ultimo_acesso.get(host, 0) + REQUEST_DELAY - time.time()
        if espera > 0:
            time.sleep(espera)
        _ultimo_acesso[host] = time.time()


def permitido(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = sessao.get(base + "/robots.txt", timeout=8)
            if r.status_code >= 400:
                _robots[base] = None
            else:
                rp.parse(r.text.splitlines())
                _robots[base] = rp
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def get(url, respeitar_robots=True, **kw):
    if respeitar_robots and not permitido(url):
        return None
    _aguardar(urlparse(url).netloc)
    try:
        r = sessao.get(url, timeout=kw.pop("timeout", 15), **kw)
        return r if r.ok else None
    except requests.RequestException:
        return None
