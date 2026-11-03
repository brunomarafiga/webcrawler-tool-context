"""
Configurações centralizadas do pipeline de extração do tool_context.
Todos os parâmetros podem ser sobrescritos via variáveis de ambiente no .env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------
CRAWL_DELAY_SECONDS: float = float(os.getenv("CRAWL_DELAY_SECONDS", "2.0"))
CRAWL_MAX_DEPTH: int = int(os.getenv("CRAWL_MAX_DEPTH", "2"))
CRAWL_MAX_PAGES_PER_TOOL: int = int(os.getenv("CRAWL_MAX_PAGES_PER_TOOL", "10"))
CRAWL_TIMEOUT_SECONDS: float = float(os.getenv("CRAWL_TIMEOUT_SECONDS", "15"))
CRAWL_MAX_RETRIES: int = int(os.getenv("CRAWL_MAX_RETRIES", "3"))

# User-Agent respeitoso para identificação do crawler
CRAWL_USER_AGENT: str = (
    "Mozilla/5.0 (compatible; ToolContextBot/1.0; "
    "+https://github.com/harmon-ia/webcrawler)"
)

# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
MIN_TEXT_LENGTH: int = int(os.getenv("MIN_TEXT_LENGTH", "100"))
MAX_TEXT_PER_PAGE: int = int(os.getenv("MAX_TEXT_PER_PAGE", "10000"))

# ---------------------------------------------------------------------------
# Generator (LLM)
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CONTEXT_MIN_CHARS: int = 600
CONTEXT_MAX_CHARS: int = 900
MAX_GENERATION_RETRIES: int = int(os.getenv("MAX_GENERATION_RETRIES", "3"))

# Número mínimo de elementos do protocolo com evidência antes de gerar
MIN_ELEMENTS_WITH_EVIDENCE: int = int(os.getenv("MIN_ELEMENTS_WITH_EVIDENCE", "3"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_PATH: Path = DATA_DIR / "pipeline.db"

# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------
INPUT_EXCEL: Path = BASE_DIR / "dataset-ferramentas.xlsx"
OUTPUT_EXCEL: Path = OUTPUT_DIR / "dataset-ferramentas-final.xlsx"
LOG_FILE: Path = LOGS_DIR / "pipeline.log"
