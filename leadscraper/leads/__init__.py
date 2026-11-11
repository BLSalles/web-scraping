import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/leads.db")
CNPJ_DIR = os.getenv("CNPJ_DIR", "data/cnpj")
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; LeadScraper/1.0)")
SEM_NAVEGADOR = os.getenv("SEM_NAVEGADOR", "").lower() in ("1", "true", "sim")
KIT_DIR = os.getenv("KIT_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "google-maps-scraper-kit"))
KIT_URL = os.getenv("KIT_URL", "http://localhost:8080").rstrip("/")
KIT_API_KEY = os.getenv("KIT_API_KEY", "")
