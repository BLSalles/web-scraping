import csv
import glob
import gzip
import io
import os
import re
import shutil
import sqlite3
import sys
import zipfile

import requests

from .. import CNPJ_DIR
from ..models import Lead
from ..normalize import sem_acento

NOME = "Base CNPJ (Receita)"
INDICE = os.path.join(CNPJ_DIR, "indice.db")
BASE_URL = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/{mes}/"
PORTE = {"00": "Não informado", "01": "ME", "03": "EPP", "05": "Demais"}
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "base")

PRESETS = {
    "solar": {
        "ufs": ["SP"],
        "sem_mei": True,
        "so_com_contato": True,
        "cnaes": [
            "4711301", "4711302", "4712100",
            "1091102", "4721102", "5611201", "5611203",
            "9313100", "5510801", "5510802",
            "4731800", "4722901", "1053800", "1052000", "9601701",
            "8610101", "8630501", "8630502", "8630503", "8630504", "8640202", "8640205",
            "8112500", "8511200", "8512100", "8513900", "8520100",
            "4771701", "4520001",
            "2539001", "2222600", "1813001",
            "0155501", "0155505", "0154700",
            "5211701", "5211799", "9491000",
        ],
    },
}

csv.field_size_limit(sys.maxsize)


def _linhas(caminho_zip):
    with zipfile.ZipFile(caminho_zip) as z:
        for nome in z.namelist():
            with z.open(nome) as f:
                yield from csv.reader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";", quotechar='"')


def _zips(prefixo):
    return sorted(glob.glob(os.path.join(CNPJ_DIR, f"{prefixo}*.zip")))


def baixar(mes, log=print):
    os.makedirs(CNPJ_DIR, exist_ok=True)
    arquivos = ["Cnaes.zip", "Municipios.zip", "Simples.zip"] + [f"Empresas{i}.zip" for i in range(10)] + [f"Estabelecimentos{i}.zip" for i in range(10)]
    for nome in arquivos:
        destino = os.path.join(CNPJ_DIR, nome)
        if os.path.exists(destino):
            log(f"já existe: {nome}")
            continue
        url = BASE_URL.format(mes=mes) + nome
        log(f"baixando {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            if not r.ok:
                log(f"erro {r.status_code}. Baixe manualmente em {BASE_URL.format(mes=mes)} e coloque em {CNPJ_DIR}")
                return
            with open(destino + ".part", "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        os.replace(destino + ".part", destino)


def importar(ufs=None, cnae_prefixos=None, sem_mei=False, so_com_contato=False, log=print):
    ufs = {u.upper() for u in ufs or []}
    cnae_prefixos = tuple(cnae_prefixos or ())
    leve = bool(cnae_prefixos)
    if not _zips("Estabelecimentos"):
        raise FileNotFoundError(f"Nenhum Estabelecimentos*.zip em {CNPJ_DIR}")

    if os.path.exists(INDICE):
        os.remove(INDICE)
    con = sqlite3.connect(INDICE)
    con.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE cnaes (codigo TEXT PRIMARY KEY, descricao TEXT, busca TEXT);
        CREATE TABLE municipios (codigo TEXT PRIMARY KEY, nome TEXT, busca TEXT);
        CREATE TABLE estab (
            cnpj TEXT PRIMARY KEY, basico TEXT, fantasia TEXT, abertura TEXT, cnae TEXT, cnaes_sec TEXT,
            logradouro TEXT, numero TEXT, complemento TEXT, bairro TEXT, cep TEXT, uf TEXT, municipio TEXT,
            tel1 TEXT, tel2 TEXT, email TEXT
        );
        CREATE TABLE empresas (basico TEXT PRIMARY KEY, razao TEXT, porte TEXT, capital TEXT);
    """)

    for zp in _zips("Cnaes"):
        con.executemany("INSERT OR IGNORE INTO cnaes VALUES (?,?,?)", ((c, d, sem_acento(d)) for c, d in _linhas(zp)))
    for zp in _zips("Municipios"):
        con.executemany("INSERT OR IGNORE INTO municipios VALUES (?,?,?)", ((c, n, sem_acento(n)) for c, n in _linhas(zp)))

    basicos = set()
    total = 0
    for zp in _zips("Estabelecimentos"):
        log(f"lendo {os.path.basename(zp)}...")
        lote = []
        for r in _linhas(zp):
            if len(r) < 28 or r[5] != "02":
                continue
            if ufs and r[19] not in ufs:
                continue
            if cnae_prefixos and not r[11].startswith(cnae_prefixos):
                continue
            tel1 = (r[21] + r[22]) if r[22] else ""
            tel2 = (r[23] + r[24]) if r[24] else ""
            if so_com_contato and not (tel1 or tel2 or r[27].strip()):
                continue
            lote.append((r[0] + r[1] + r[2], r[0], r[4], r[10], r[11], "" if leve else r[12], f"{r[13]} {r[14]}".strip(), r[15], r[16],
                         r[17], r[18], r[19], r[20], tel1, tel2, r[27].lower()))
            basicos.add(r[0])
            if len(lote) >= 50000:
                con.executemany("INSERT OR IGNORE INTO estab VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", lote)
                total += len(lote)
                lote = []
        con.executemany("INSERT OR IGNORE INTO estab VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", lote)
        total += len(lote)
        log(f"  {total:,} estabelecimentos ativos até agora".replace(",", "."))

    if sem_mei:
        zs = _zips("Simples")
        if not zs:
            log("Simples.zip não encontrado: não dá pra tirar os MEI, seguindo com eles.")
        else:
            meis = set()
            for zp in zs:
                log(f"lendo {os.path.basename(zp)} (identificando MEI)...")
                meis.update(r[0] for r in _linhas(zp) if len(r) >= 5 and r[4] == "S" and r[0] in basicos)
            if meis:
                con.execute("CREATE TEMP TABLE meis (basico TEXT PRIMARY KEY)")
                con.executemany("INSERT OR IGNORE INTO meis VALUES (?)", ((b,) for b in meis))
                con.execute("DELETE FROM estab WHERE basico IN (SELECT basico FROM meis)")
                basicos -= meis
                total = con.execute("SELECT COUNT(*) FROM estab").fetchone()[0]
                log(f"  {len(meis):,} MEI removidos, ficaram {total:,}".replace(",", "."))

    for zp in _zips("Empresas"):
        log(f"lendo {os.path.basename(zp)}...")
        lote = [(r[0], r[1], r[5], r[4]) for r in _linhas(zp) if len(r) >= 6 and r[0] in basicos]
        con.executemany("INSERT OR IGNORE INTO empresas VALUES (?,?,?,?)", lote)

    if leve:
        con.execute("DELETE FROM cnaes WHERE codigo NOT IN (SELECT DISTINCT cnae FROM estab)")

    log("criando índices...")
    con.executescript("""
        CREATE INDEX ix_estab_mun_cnae ON estab (municipio, cnae);
        CREATE INDEX ix_estab_uf_cnae ON estab (uf, cnae);
        CREATE INDEX ix_estab_abertura ON estab (abertura);
    """)
    con.commit()
    con.execute("VACUUM")
    con.close()
    log(f"pronto: {total:,} estabelecimentos em {INDICE}".replace(",", "."))


def importar_preset(nome, log=print):
    cfg = PRESETS[nome]
    importar(cfg["ufs"], cfg["cnaes"], cfg["sem_mei"], cfg["so_com_contato"], log)
    return publicar(nome, log)


def publicar(nome, log=print):
    os.makedirs(BASE_DIR, exist_ok=True)
    destino = os.path.join(BASE_DIR, f"indice_{nome}.db.gz")
    with open(INDICE, "rb") as f, gzip.open(destino, "wb", compresslevel=9) as g:
        shutil.copyfileobj(f, g, 1 << 20)
    mb = os.path.getsize(destino) / 1e6
    log(f"base compactada em {os.path.relpath(destino)} ({mb:.1f} MB)")
    if mb > 95:
        log("ATENÇÃO: passou de 95 MB, o GitHub recusa arquivos acima de 100 MB. Reduza os CNAEs ou a UF.")
    return destino


def instalar_base(log=print):
    if os.path.exists(INDICE):
        return True
    pacotes = sorted(glob.glob(os.path.join(BASE_DIR, "indice_*.db.gz")))
    if not pacotes:
        return False
    os.makedirs(CNPJ_DIR, exist_ok=True)
    log(f"descompactando {os.path.basename(pacotes[0])}...")
    with gzip.open(pacotes[0], "rb") as g, open(INDICE + ".part", "wb") as f:
        shutil.copyfileobj(g, f, 1 << 20)
    os.replace(INDICE + ".part", INDICE)
    return True


def cnaes_por_termo(con, termo):
    termo = sem_acento(termo).strip()
    if termo in ("*", "todos", "tudo", "todas"):
        return [r[0] for r in con.execute("SELECT codigo FROM cnaes")]
    if re.fullmatch(r"[\d,\s./-]+", termo):
        return [re.sub(r"\D", "", c) for c in termo.split(",") if re.sub(r"\D", "", c)]
    palavras = [w for w in re.split(r"\s+", termo) if len(w) > 2]
    if not palavras:
        return []
    radicais = [w[:-1] if len(w) > 4 and w.endswith("s") else w for w in palavras]
    sql = "SELECT codigo FROM cnaes WHERE " + " AND ".join("busca LIKE ?" for _ in radicais)
    return [r[0] for r in con.execute(sql, [f"%{w}%" for w in radicais])]


def buscar(p, log):
    if not instalar_base(log):
        log("Base CNPJ não encontrada. No seu PC rode: python cli.py cnpj-baixar AAAA-MM e depois python cli.py cnpj-importar --preset solar")
        return
    con = sqlite3.connect(INDICE)
    con.row_factory = sqlite3.Row

    codigos = cnaes_por_termo(con, p.get("cnae") or p["nicho"])
    if not codigos:
        log(f"Nenhum CNAE bate com '{p.get('cnae') or p['nicho']}'. Tente palavras da descrição oficial ou informe o código CNAE.")
        return
    descr = [r[0] for r in con.execute(f"SELECT descricao FROM cnaes WHERE codigo IN ({','.join('?' * len(codigos))})", codigos)]
    log(f"CNAEs usados ({len(codigos)}): " + "; ".join(descr[:5]) + (" ..." if len(descr) > 5 else ""))

    where, args = [f"(e.cnae IN ({','.join('?' * len(codigos))})" + (" OR " + " OR ".join("e.cnaes_sec LIKE ?" for _ in codigos) if p.get("cnae_secundario") else "") + ")"], list(codigos)
    if p.get("cnae_secundario"):
        args += [f"%{c}%" for c in codigos]
    if p.get("cidade"):
        muns = [r[0] for r in con.execute("SELECT codigo FROM municipios WHERE busca = ?", (sem_acento(p["cidade"]),))]
        if not muns:
            log(f"Município '{p['cidade']}' não encontrado na base.")
            return
        where.append(f"e.municipio IN ({','.join('?' * len(muns))})")
        args += muns
    if p.get("uf"):
        where.append("e.uf = ?")
        args.append(p["uf"].upper())
    if p.get("so_com_contato"):
        where.append("(e.tel1 != '' OR e.email != '')")
    if p.get("aberta_desde"):
        where.append("e.abertura >= ?")
        args.append(re.sub(r"\D", "", p["aberta_desde"]))
    if p.get("porte"):
        where.append(f"emp.porte IN ({','.join('?' * len(p['porte']))})")
        args += p["porte"]

    sql = f"""
        SELECT e.*, emp.razao, emp.porte, m.nome AS cidade
        FROM estab e
        LEFT JOIN empresas emp ON emp.basico = e.basico
        LEFT JOIN municipios m ON m.codigo = e.municipio
        WHERE {' AND '.join(where)}
        ORDER BY e.abertura DESC
        LIMIT ?
    """
    args.append(p["limite"])
    n = 0
    for r in con.execute(sql, args):
        n += 1
        ab = r["abertura"]
        yield Lead(
            nome=r["fantasia"] or r["razao"] or "",
            razao_social=r["razao"] or "",
            cnpj=r["cnpj"],
            telefone=r["tel1"],
            telefones_extras=[r["tel2"]] if r["tel2"] else [],
            email=r["email"],
            endereco=", ".join(x for x in (r["logradouro"], r["numero"], r["complemento"]) if x),
            bairro=r["bairro"],
            cidade=(r["cidade"] or "").title(),
            uf=r["uf"],
            cep=r["cep"],
            cnae=r["cnae"],
            porte=PORTE.get(r["porte"] or "", ""),
            abertura=f"{ab[6:8]}/{ab[4:6]}/{ab[:4]}" if len(ab) == 8 else "",
            fontes=["cnpj"],
        )
    log(f"{n} empresas encontradas na base CNPJ")
    con.close()
