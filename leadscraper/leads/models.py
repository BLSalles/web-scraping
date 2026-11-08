from dataclasses import dataclass, field, asdict

CAMPOS_EXPORT = [
    "nome", "razao_social", "cnpj", "telefone", "whatsapp", "email", "site",
    "instagram", "facebook", "linkedin", "endereco", "bairro", "cidade", "uf", "cep",
    "cnae", "porte", "abertura", "nota", "avaliacoes", "maps_url", "fontes", "status",
]


@dataclass
class Lead:
    nome: str = ""
    razao_social: str = ""
    cnpj: str = ""
    telefone: str = ""
    whatsapp: str = ""
    email: str = ""
    site: str = ""
    instagram: str = ""
    facebook: str = ""
    linkedin: str = ""
    endereco: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    cnae: str = ""
    porte: str = ""
    abertura: str = ""
    nota: float | None = None
    avaliacoes: int | None = None
    maps_url: str = ""
    fontes: list[str] = field(default_factory=list)
    telefones_extras: list[str] = field(default_factory=list)
    emails_extras: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
