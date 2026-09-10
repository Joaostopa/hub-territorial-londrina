"""Configuração independente do diretório de execução."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATA_DIR = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
DEMO_DATABASE_URL = f'sqlite:///{DATA_DIR / "demo.db"}'
AUTH_REQUIRED = os.getenv('AUTH_REQUIRED', 'false').lower() == 'true'
ALLOWED_EMAILS = {e.strip().lower() for e in os.getenv('ALLOWED_EMAILS', '').split(',') if e.strip()}
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()}
USER_AGENT = os.getenv('HTTP_USER_AGENT', 'ImoveisHub/2.0 (internal market research)')
CITIES = {
    'Londrina': {'code': '4113700', 'state': 'PR', 'lat': -23.3045, 'lon': -51.1696},
    'Maringá': {'code': '4115200', 'state': 'PR', 'lat': -23.4205, 'lon': -51.9331},
    'Curitiba': {'code': '4106902', 'state': 'PR', 'lat': -25.4284, 'lon': -49.2733},
    'Campinas': {'code': '3509502', 'state': 'SP', 'lat': -22.9056, 'lon': -47.0608},
    'Sorocaba': {'code': '3552205', 'state': 'SP', 'lat': -23.5015, 'lon': -47.4526},
    'Campo Grande': {'code': '5002704', 'state': 'MS', 'lat': -20.4697, 'lon': -54.6201},
}
