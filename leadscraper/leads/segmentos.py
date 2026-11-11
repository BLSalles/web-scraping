from .normalize import sem_acento

SOLAR = [
    "supermercado", "padaria", "restaurante", "academia", "hotel", "posto de combustível",
    "clínica", "escola", "condomínio", "indústria", "granja",
]


def expandir(nicho):
    return SOLAR if sem_acento(nicho) in ("todos", "todas", "tudo", "*") else [nicho]
