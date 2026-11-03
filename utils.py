"""
Utilitários compartilhados: logging, retry e classificação de fonte.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from config import LOG_FILE, LOGS_DIR


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configura logging para console e arquivo."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)
    return logging.getLogger("pipeline")


def classify_source(url: str) -> str:
    """Classifica a origem de uma URL em categorias padronizadas."""
    parsed = urlparse(url.lower())
    netloc = parsed.netloc
    path = parsed.path

    if any(h in netloc for h in ["github.com", "gitlab.com", "bitbucket.org"]):
        return "repositorio"
    if any(
        h in netloc
        for h in ["readthedocs.io", "docs.", "documentation.", "help.", "support."]
    ):
        return "documentacao"
    if any(
        kw in path
        for kw in ["/docs", "/documentation", "/help", "/guide", "/tutorial"]
    ):
        return "documentacao"
    if any(kw in path for kw in ["/install", "/setup", "/getting-started", "/quickstart"]):
        return "guia_instalacao"
    if any(kw in path for kw in ["/pricing", "/plans", "/price"]):
        return "precos"
    return "pagina_oficial"


def clean_url(url: str) -> str:
    """Remove fragmentos e parâmetros de rastreamento desnecessários."""
    url = url.strip().rstrip("/")
    # Remover âncoras
    url = re.sub(r"#.*$", "", url)
    return url


def is_same_domain(url: str, reference_url: str) -> bool:
    """Verifica se dois URLs compartilham o mesmo domínio base."""
    try:
        ref_netloc = urlparse(reference_url).netloc.lstrip("www.")
        url_netloc = urlparse(url).netloc.lstrip("www.")
        return url_netloc == ref_netloc or url_netloc.endswith(f".{ref_netloc}")
    except Exception:
        return False


def is_likely_useful_path(path: str) -> bool:
    """Filtra caminhos que provavelmente não têm conteúdo útil."""
    skip_patterns = [
        r"\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|pdf|zip|tar|gz)$",
        r"/(login|signup|register|cart|checkout|account|profile|settings)(/|$)",
        r"/(tag|category|author|feed|rss|sitemap)(/|$)",
        r"/page/\d+",
    ]
    path_lower = path.lower()
    return not any(re.search(p, path_lower) for p in skip_patterns)
