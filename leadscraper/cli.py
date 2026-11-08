import argparse
import sys

from leads import db
from leads.export import csv_bytes, xlsx_bytes
from leads.pipeline import rodar
from leads.sources import FONTES, cnpj


def main():
    ap = argparse.ArgumentParser(description="LeadScraper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("buscar", help="roda uma busca e salva no banco")
    b.add_argument("nicho")
    b.add_argument("--cidade", default="")
    b.add_argument("--uf", default="")
    b.add_argument("--fontes", default="google_maps", help=f"separadas por vírgula: {','.join(FONTES)}")
    b.add_argument("--limite", type=int, default=50)
    b.add_argument("--cnae", default="")
    b.add_argument("--urls", default="")
    b.add_argument("--sem-enriquecer", action="store_true")

    d = sub.add_parser("cnpj-baixar", help="baixa os zips da Receita")
    d.add_argument("mes", help="AAAA-MM, ex.: 2026-10")

    i = sub.add_parser("cnpj-importar", help="monta o índice local a partir dos zips")
    i.add_argument("--uf", action="append", help="pode repetir: --uf SP --uf MG")
    i.add_argument("--cnae-prefixo", action="append", help="filtra CNAE principal, ex.: --cnae-prefixo 86")

    e = sub.add_parser("exportar")
    e.add_argument("arquivo", help="leads.xlsx ou leads.csv")
    e.add_argument("--status")

    a = ap.parse_args()

    if a.cmd == "buscar":
        params = dict(nicho=a.nicho, cidade=a.cidade, uf=a.uf.upper(), limite=a.limite, cnae=a.cnae, urls=a.urls,
                      so_com_contato=True, headless=True)
        rodar(params, [f.strip() for f in a.fontes.split(",") if f.strip() in FONTES], not a.sem_enriquecer)
    elif a.cmd == "cnpj-baixar":
        cnpj.baixar(a.mes)
    elif a.cmd == "cnpj-importar":
        cnpj.importar(a.uf, a.cnae_prefixo)
    elif a.cmd == "exportar":
        dados = db.listar(status=a.status)
        conteudo = xlsx_bytes(dados) if a.arquivo.endswith(".xlsx") else csv_bytes(dados)
        with open(a.arquivo, "wb") as f:
            f.write(conteudo)
        print(f"{len(dados)} leads em {a.arquivo}")


if __name__ == "__main__":
    sys.exit(main())
