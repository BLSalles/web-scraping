# LeadScraper

Captação de leads B2B com cinco fontes selecionáveis, painel web e fila de abordagem por WhatsApp (manual assistida, sem API).

| Fonte | O que traz | Observação |
|---|---|---|
| OpenStreetMap | nome, telefone, WhatsApp, site, e-mail, endereço | Grátis, sem chave e sem navegador (API Overpass). Cobertura no Brasil é menor que a do Google, varia por cidade |
| Google Maps | nome, telefone, site, endereço, nota, nº de avaliações | Com `GOOGLE_PLACES_API_KEY` usa a Places API oficial; sem chave, usa navegador (Playwright) |
| Base CNPJ (Receita) | razão social, CNPJ, CNAE, porte, abertura, telefone e e-mail cadastrados | Dados abertos; precisa importar a base uma vez |
| Sites | e-mails, WhatsApp, Instagram/Facebook/LinkedIn, CNPJ | Varre home + páginas de contato, respeita robots.txt |
| Diretórios | o que o site de listagem mostrar | Configurável por seletor CSS em `diretorios.yaml` |

Leads com CNPJ são completados pelo [OpenCNPJ](https://opencnpj.org) (grátis, consulta por CNPJ). Os resultados de todas as fontes são unificados (CNPJ, domínio, telefone e nome+cidade) e, opcionalmente, os sites encontrados são visitados para completar e-mail e WhatsApp.

## Rodar local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
playwright install chromium
copy .env.example .env          # Linux/Mac: cp
python app.py
```

Abra http://localhost:5000

## Base CNPJ

### Pacote energia solar (recomendado)

Empresas ativas de SP, sem MEI, com telefone ou e-mail, nos ramos com conta de luz alta (supermercados, padarias, restaurantes, academias, hotéis, postos, clínicas, hospitais, escolas, condomínios, indústrias leves, granjas, armazéns, igrejas...). Roda no seu PC e gera `base/indice_solar.db.gz`, que sobe pro GitHub junto com o código; o servidor descompacta sozinho na primeira busca.

```bash
python cli.py cnpj-baixar 2026-10
python cli.py cnpj-importar --preset solar
```

Na busca, use o nicho `todos` para trazer todos os ramos do pacote, ou um ramo específico (`supermercados`, `restaurantes`, `condominios`...).

### Base personalizada

São ~8 GB de zips. Baixe só uma vez e importe filtrando pelo que interessa, para o índice ficar pequeno:

```bash
python cli.py cnpj-baixar 2026-10
python cli.py cnpj-importar --uf SP
python cli.py cnpj-importar --uf SP --cnae-prefixo 86 --cnae-prefixo 69   # mais enxuto
```

Se o download automático falhar, baixe os arquivos em https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/ (pasta do mês) e coloque em `data/cnpj/`: `Cnaes.zip`, `Municipios.zip`, `Empresas0-9.zip`, `Estabelecimentos0-9.zip`.

Na busca, o nicho é casado com a descrição oficial do CNAE ("odontológica", "contabilidade", "academia"). Para precisão, informe o código CNAE.

## WhatsApp

Aba **WhatsApp**: crie um modelo com variáveis (`{nome}`, `{cidade}`, `{bairro}`...), carregue a fila e, para cada lead, clique em **Abrir conversa** (abre o WhatsApp Web ou app com o texto pronto), envie e clique em **Enviei**. O lead vira `contatado` e a fila avança.

O painel aplica intervalo mínimo aleatório entre conversas e limite diário. Quem pedir para sair vai pra lista de opt-out e não aparece mais na fila. Para não ter o número bloqueado:

- use um número de WhatsApp Business dedicado e "aquecido" (com uso normal antes);
- comece com 10–20 por dia e só depois aumente;
- mensagem curta, personalizada, com pergunta, sem link na primeira mensagem;
- respeite quem pede para sair.

## Linha de comando

```bash
python cli.py buscar "clínica odontológica" --cidade Suzano --uf SP --fontes google_maps,cnpj --limite 100
python cli.py exportar leads.xlsx
```

## Deploy no Render

1. Suba o projeto no GitHub.
2. No Render: **New > Blueprint**, escolha o repositório (ele lê o `render.yaml`).
3. Preencha `APP_PASSWORD`, defina `SEM_NAVEGADOR=1` no plano gratuito (512 MB não comportam o navegador) (senha do painel; usuário padrão `admin`) e, se tiver, `GOOGLE_PLACES_API_KEY`.

O blueprint usa plano pago com disco de 5 GB em `/var/data`, onde ficam o banco e a base CNPJ. No plano gratuito o app dorme sem uso e o disco é apagado a cada deploy, então os leads se perdem.

Base CNPJ no servidor: rode `cnpj-importar` localmente com filtro de UF/CNAE e envie só o `data/cnpj/indice.db` para `/var/data/cnpj/` (pelo Shell do Render ou `scp`), em vez de baixar os 8 GB lá.

## LGPD e boas práticas

- O foco é B2B (dados de empresas). Telefone/e-mail de MEI e empresário individual podem ser dado pessoal: trate com base em legítimo interesse, use só para oferta relacionada ao negócio e sempre ofereça saída.
- Não raspe sites que proíbem nos termos de uso; o raspador respeita `robots.txt` por padrão.
- O scraping do Google Maps via navegador é frágil (o layout muda) e vai contra os termos do Google; para uso contínuo prefira a Places API.

## Testes

```bash
pip install pytest
python -m pytest -q
```
