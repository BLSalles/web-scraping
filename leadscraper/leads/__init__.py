import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/leads.db")
CNPJ_DIR = os.getenv("CNPJ_DIR", "data/cnpj")
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.5"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; LeadScraper/1.0)")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
