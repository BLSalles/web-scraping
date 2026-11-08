import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import CAMPOS_EXPORT
from .normalize import telefone_formatado


def _linha(d):
    out = []
    for c in CAMPOS_EXPORT:
        v = d.get(c, "")
        if c in ("telefone", "whatsapp"):
            v = telefone_formatado(v)
        elif c == "fontes":
            v = ", ".join(v)
        out.append("" if v is None else v)
    return out


def csv_bytes(leads):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(CAMPOS_EXPORT)
    for d in leads:
        w.writerow(_linha(d))
    return buf.getvalue().encode("utf-8-sig")


def xlsx_bytes(leads):
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    ws.append([c.replace("_", " ").title() for c in CAMPOS_EXPORT])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    for d in leads:
        ws.append(_linha(d))
    for i, c in enumerate(CAMPOS_EXPORT, 1):
        ws.column_dimensions[get_column_letter(i)].width = 38 if c in ("nome", "razao_social", "endereco", "email", "site", "maps_url") else 16
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
