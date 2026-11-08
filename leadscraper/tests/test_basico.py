import importlib
import io
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "leads.db"))
    monkeypatch.setenv("CNPJ_DIR", str(tmp_path / "cnpj"))
    monkeypatch.setenv("APP_PASSWORD", "")
    import leads
    importlib.reload(leads)
    for m in ("leads.db", "leads.sources.cnpj"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    yield tmp_path


def test_normalizacao():
    from leads.normalize import telefone, email, dominio, eh_celular
    assert telefone("(11) 98765-4321") == "5511987654321"
    assert telefone("+55 11 3456-7890") == "551134567890"
    assert telefone("011 3456-7890") == "551134567890"
    assert telefone("123") == ""
    assert eh_celular("11987654321") and not eh_celular("1134567890")
    assert email("Contato@Empresa.com.br") == "contato@empresa.com.br"
    assert email("logo@2x.png") == ""
    assert dominio("https://www.empresa.com.br/contato") == "empresa.com.br"
    assert dominio("https://instagram.com/x") == ""


def test_deduplicacao_junta_fontes():
    from leads.models import Lead
    from leads.normalize import deduplicar
    a = Lead(nome="Clínica Sorriso", telefone="(11) 98765-4321", cidade="Suzano", fontes=["google_maps"])
    b = Lead(nome="CLINICA SORRISO", razao_social="SORRISO LTDA", cnpj="12.345.678/0001-90", telefone="11987654321",
             email="contato@sorriso.com.br", cidade="Suzano", fontes=["cnpj"])
    c = Lead(nome="Outra", telefone="1133334444", cidade="Suzano", fontes=["cnpj"])
    out = deduplicar([a, b, c])
    assert len(out) == 2
    s = out[0]
    assert s.cnpj == "12345678000190" and s.email == "contato@sorriso.com.br"
    assert s.whatsapp == "5511987654321" and s.fontes == ["cnpj", "google_maps"]


def test_extracao_site(monkeypatch):
    from leads import http
    from leads.sources import websites
    paginas = {
        "https://sorriso.com.br": """<html><title>Clínica Sorriso</title><body>
            <a href="/contato">Contato</a><a href="https://wa.me/5511987654321">Zap</a>
            <a href="https://instagram.com/sorriso?igsh=1">insta</a> CNPJ 12.345.678/0001-90</body></html>""",
        "https://sorriso.com.br/contato": """<html><body>Ligue (11) 4747-1234 ou
            <a href="mailto:contato@sorriso.com.br">email</a> marketing@gmail.com <img src="x@2x.png"></body></html>""",
    }

    class R:
        def __init__(self, t): self.text, self.headers = t, {"content-type": "text/html"}

    monkeypatch.setattr(http, "get", lambda url, **k: R(paginas[url]) if url in paginas else None)
    d = websites.extrair("sorriso.com.br")
    assert d["whatsapp"] == "5511987654321"
    assert d["emails"][0] == "contato@sorriso.com.br"
    assert "551147471234" in d["telefones"]
    assert d["instagram"] == "https://instagram.com/sorriso"
    assert d["cnpj"] == "12345678000190"


def _zip(caminho, nome, linhas):
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(nome, "\n".join(";".join(f'"{c}"' for c in l) for l in linhas).encode("latin-1"))


def test_cnpj_importa_e_busca(ambiente):
    from leads.sources import cnpj
    d = ambiente / "cnpj"
    d.mkdir()
    _zip(d / "Cnaes.zip", "c.csv", [["8630504", "Atividade odontológica"], ["4711302", "Comércio varejista de mercadorias - supermercados"]])
    _zip(d / "Municipios.zip", "m.csv", [["7171", "SUZANO"], ["7075", "SAO PAULO"]])

    def est(basico, sit, cnae, mun, uf, fantasia, tel, email):
        r = [""] * 30
        r[0], r[1], r[2], r[4], r[5], r[10], r[11] = basico, "0001", "90", fantasia, sit, "20230115", cnae
        r[13], r[14], r[15], r[17], r[18], r[19], r[20] = "RUA", "A", "10", "CENTRO", "08600000", uf, mun
        r[21], r[22], r[27] = "11", tel, email
        return r

    _zip(d / "Estabelecimentos0.zip", "e.csv", [
        est("11111111", "02", "8630504", "7171", "SP", "SORRISO", "987654321", "CONTATO@SORRISO.COM.BR"),
        est("22222222", "08", "8630504", "7171", "SP", "BAIXADA", "33334444", ""),
        est("33333333", "02", "4711302", "7171", "SP", "MERCADO", "33335555", ""),
        est("44444444", "02", "8630504", "7075", "SP", "OUTRA CIDADE", "33336666", ""),
    ])
    _zip(d / "Empresas0.zip", "emp.csv", [["11111111", "SORRISO ODONTO LTDA", "2062", "49", "10000,00", "01", ""]])

    cnpj.importar(ufs=["SP"], log=lambda *_: None)
    out = list(cnpj.buscar({"nicho": "odontológica", "cidade": "Suzano", "uf": "SP", "limite": 10}, lambda *_: None))
    assert len(out) == 1
    l = out[0]
    assert l.nome == "SORRISO" and l.razao_social == "SORRISO ODONTO LTDA" and l.porte == "ME"
    assert l.cnpj == "11111111000190" and l.cidade == "Suzano" and l.abertura == "15/01/2023"


def test_db_whatsapp_e_api(ambiente):
    from leads import db
    from leads.models import Lead
    from leads.normalize import deduplicar
    db.salvar(deduplicar([Lead(nome="Sorriso LTDA", telefone="11987654321", cidade="Suzano", fontes=["x"])]), "teste")
    novos, atual = db.salvar(deduplicar([Lead(nome="Sorriso", telefone="(11) 98765-4321", email="a@b.com.br", cidade="Suzano")]), "teste")
    assert (novos, atual) == (0, 1)

    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    leads = c.get("/api/leads").get_json()["leads"]
    assert len(leads) == 1 and leads[0]["email"] == "a@b.com.br"
    modelo = c.get("/api/modelos").get_json()["modelos"][0]
    fila = c.get(f"/api/fila?modelo={modelo['id']}&web=1").get_json()["fila"]
    assert fila[0]["link"].startswith("https://web.whatsapp.com/send?phone=5511987654321&text=Ol")
    assert "Sorriso" in fila[0]["texto"] and "LTDA" not in fila[0]["texto"]

    c.post(f"/api/leads/{leads[0]['id']}/status", json={"status": "contatado"})
    assert c.get(f"/api/fila?modelo={modelo['id']}").get_json()["fila"] == []
    assert c.get("/exportar.xlsx").status_code == 200
    assert c.get("/").status_code == 200


def test_login(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "segredo")
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    assert c.get("/").status_code == 401
    assert c.get("/saude").status_code == 200
    assert c.get("/", auth=("admin", "segredo")).status_code == 200
