"""Configuracoes centrais do bot, lidas do arquivo .env."""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SEARCH_RADIUS = int(os.getenv("SEARCH_RADIUS", "15000"))
PROXIMITY_ALERT = int(os.getenv("PROXIMITY_ALERT", "3000"))

# --- Autonomia da moto (Harley-Davidson Heritage Softail Classic) ---
# Tanque de 5 galoes (18,9 L). Consumo conservador de 17 km/L (~40 MPG, real
# em estrada com carga/calor/vento). Mantemos ~1 galao (3,8 L) de reserva, entao
# o bot calcula com a autonomia SEGURA, nao com o tanque cheio teorico.
TANQUE_LITROS = float(os.getenv("TANQUE_LITROS", "18.9"))
CONSUMO_KM_L = float(os.getenv("CONSUMO_KM_L", "17"))
RESERVA_LITROS = float(os.getenv("RESERVA_LITROS", "3.8"))

# Caminho do banco SQLite e da planilha da rota
DB_PATH = os.getenv("DB_PATH", "rota66.db")
EXCEL_PATH = os.getenv("EXCEL_PATH", "rota.xlsx")

# User-Agent obrigatorio para usar o Nominatim (politica de uso do OpenStreetMap)
USER_AGENT = "Rota66TripBot/1.0 (contato: seu-email@exemplo.com)"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN nao definido. Copie .env.example para .env e preencha.")
