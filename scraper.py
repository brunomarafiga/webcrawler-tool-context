"""
Web Scraper: extrai conteúdo textual útil de cada URL descoberta pelo crawler.

Usa trafilatura como extrator principal (ótimo para conteúdo editorial)
com fallback para BeautifulSoup quando trafilatura não retorna resultado suficiente.
Registra cada evidência no banco com rastreabilidade completa.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from config import CRAWL_DELAY_SECONDS, CRAWL_TIMEOUT_SECONDS, CRAWL_USER_AGENT, MAX_TEXT_PER_PAGE, MIN_TEXT_LENGTH
from database import Database
from models import EvidenceRecord, ScrapeStatus
from utils import classify_source

log = logging.getLogger("pipeline.scraper")


def _scrape_with_trafilatura(html: str) -> str | None:
    """Extrai texto limpo usando trafilatura."""
    return trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        deduplicate=True,
        no_fallback=False,
    )


def _scrape_with_beautifulsoup(html: str) -> str:
    """Extração de fallback usando BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    # Remover elementos sem valor informativo
    for tag in soup(
        ["nav", "footer", "header", "script", "style", "aside",
         "noscript", "iframe", "form", "button", "figure"]
    ):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_title(html: str) -> str:
    """Extrai o título da página."""
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    # Tentar og:title como fallback
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    # Tentar h1
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def scrape_urls(
    urls: list[str],
    tool_id: int,
    db: Database,
) -> list[EvidenceRecord]:
    """
    Faz scraping de uma lista de URLs e persiste as evidências no banco.
    Retorna apenas registros com conteúdo suficiente.
    """
    evidences: list[EvidenceRecord] = []
    headers = {
        "User-Agent": CRAWL_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    with httpx.Client(
        timeout=CRAWL_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=headers,
    ) as client:

        for url in urls:
            log.debug(f"[{tool_id}] Scraping: {url}")

            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    log.debug(f"[{tool_id}] HTTP {resp.status_code}: {url}")
                    continue
                html = resp.text
            except (httpx.TimeoutException, httpx.RequestError) as e:
                log.warning(f"[{tool_id}] Erro scraping {url}: {e}")
                continue

            # Extração com trafilatura
            extracted = _scrape_with_trafilatura(html)
            method = "trafilatura"

            if not extracted or len(extracted) < MIN_TEXT_LENGTH:
                extracted = _scrape_with_beautifulsoup(html)
                method = "beautifulsoup_fallback"

            if not extracted or len(extracted) < MIN_TEXT_LENGTH:
                log.debug(f"[{tool_id}] Conteúdo insuficiente em: {url}")
                record = EvidenceRecord(
                    tool_id=tool_id,
                    source_url=url,
                    source_type=classify_source(url),
                    page_title=_extract_title(html),
                    extracted_text="",
                    extraction_method=method,
                    extracted_at=datetime.now(),
                    scrape_status=ScrapeStatus.SKIPPED,
                    content_hash="",
                    context_element=None,
                    evidence_excerpt="",
                )
                db.save_evidence(record)
                continue

            # Limitar tamanho do texto armazenado
            text = extracted[:MAX_TEXT_PER_PAGE]
            status = (
                ScrapeStatus.PARTIAL
                if len(extracted) > MAX_TEXT_PER_PAGE
                else ScrapeStatus.COMPLETED
            )

            record = EvidenceRecord(
                tool_id=tool_id,
                source_url=url,
                source_type=classify_source(url),
                page_title=_extract_title(html),
                extracted_text=text,
                extraction_method=method,
                extracted_at=datetime.now(),
                scrape_status=status,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                context_element=None,
                evidence_excerpt="",
            )
            db.save_evidence(record)
            evidences.append(record)

            log.debug(
                f"[{tool_id}] Extraídos {len(text)} chars via {method}: {url}"
            )
            time.sleep(CRAWL_DELAY_SECONDS)

    log.info(f"[{tool_id}] Scraping concluído. Evidências úteis: {len(evidences)}")
    return evidences
