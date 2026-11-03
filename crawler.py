"""
Web Crawler: descobre e registra páginas oficiais relevantes para cada ferramenta.

Responsabilidades:
- Aceitar as URLs seed da ferramenta (official, docs, repo)
- Verificar acessibilidade de cada URL (HTTP status)
- Descobrir links internos relevantes até profundidade CRAWL_MAX_DEPTH
- Respeitar robots.txt (via verificação de cabeçalhos e heurísticas)
- Registrar cada tentativa em crawl_log no banco
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    CRAWL_DELAY_SECONDS,
    CRAWL_MAX_DEPTH,
    CRAWL_MAX_PAGES_PER_TOOL,
    CRAWL_TIMEOUT_SECONDS,
    CRAWL_USER_AGENT,
)
from database import Database
from models import CrawlRecord, CrawlStatus, Tool
from utils import clean_url, classify_source, is_likely_useful_path, is_same_domain

log = logging.getLogger("pipeline.crawler")

# Cache de robots.txt para evitar buscas repetidas
_robots_cache: dict[str, RobotFileParser] = {}


def _get_robots(base_url: str, client: httpx.Client) -> RobotFileParser | None:
    """Busca e faz parse do robots.txt do domínio."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url in _robots_cache:
        return _robots_cache[robots_url]

    try:
        resp = client.get(robots_url, timeout=5)
        if resp.status_code == 200:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.parse(resp.text.splitlines())
            _robots_cache[robots_url] = rp
            return rp
    except Exception:
        pass
    return None


def _is_robots_allowed(url: str, client: httpx.Client) -> bool:
    """Verifica se o crawler tem permissão para acessar a URL."""
    rp = _get_robots(url, client)
    if rp is None:
        return True  # Sem robots.txt → permitido por padrão
    return rp.can_fetch(CRAWL_USER_AGENT, url)


def _extract_links(html: str, base_url: str, tool: Tool) -> list[str]:
    """Extrai links relevantes de uma página HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        full_url = clean_url(urljoin(base_url, href))
        parsed = urlparse(full_url)

        # Apenas http/https
        if parsed.scheme not in ("http", "https"):
            continue

        # Apenas caminhos que podem ter conteúdo útil
        if not is_likely_useful_path(parsed.path):
            continue

        # Apenas mesmo domínio das seeds ou domínios cadastrados
        is_relevant = any(
            is_same_domain(full_url, seed)
            for seed in tool.seed_urls()
            if seed
        )
        if is_relevant:
            links.append(full_url)

    return list(dict.fromkeys(links))  # Deduplica mantendo ordem


def crawl_tool(tool: Tool, db: Database) -> list[str]:
    """
    Crawla as páginas de uma ferramenta e retorna URLs com conteúdo acessível.
    Persiste todos os registros no banco de dados.
    """
    log.info(f"[{tool.id}] Crawling: {tool.name} — seeds: {tool.seed_urls()}")

    discovered_urls: list[str] = []
    visited: set[str] = set()

    # Fila: (url, depth, parent_url, seed_url)
    queue: list[tuple[str, int, str, str]] = [
        (url, 0, url, url) for url in tool.seed_urls()
    ]

    headers = {
        "User-Agent": CRAWL_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Usamos cliente síncrono para simplicidade no controle de delay
    with httpx.Client(
        timeout=CRAWL_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers=headers,
        max_redirects=5,
    ) as client:

        while queue:
            url, depth, parent_url, seed_url = queue.pop(0)
            url = clean_url(url)

            if url in visited:
                continue
            if len(discovered_urls) >= CRAWL_MAX_PAGES_PER_TOOL:
                log.debug(f"[{tool.id}] Limite de páginas atingido.")
                break
            if depth > CRAWL_MAX_DEPTH:
                continue

            visited.add(url)

            # Verificar robots.txt
            robots_ok = _is_robots_allowed(url, client)
            if not robots_ok:
                log.debug(f"[{tool.id}] Bloqueado por robots.txt: {url}")
                db.save_crawl(
                    CrawlRecord(
                        tool_id=tool.id,
                        seed_url=seed_url,
                        discovered_url=url,
                        parent_url=parent_url,
                        crawl_depth=depth,
                        robots_allowed=False,
                        http_status=None,
                        content_type="",
                        crawled_at=datetime.now(),
                        crawl_status=CrawlStatus.SKIPPED,
                    )
                )
                continue

            # Requisição HTTP
            html: str | None = None
            http_status: int | None = None
            content_type: str = ""
            status = CrawlStatus.ERROR

            try:
                resp = client.get(url)
                http_status = resp.status_code
                content_type = resp.headers.get("content-type", "")

                if resp.status_code == 200 and "text/html" in content_type:
                    html = resp.text
                    status = CrawlStatus.COMPLETED
                    discovered_urls.append(url)
                    log.debug(f"[{tool.id}] OK [{depth}]: {url}")
                else:
                    status = CrawlStatus.SKIPPED
                    log.debug(
                        f"[{tool.id}] Ignorado (HTTP {http_status}): {url}"
                    )
            except httpx.TimeoutException:
                log.warning(f"[{tool.id}] Timeout: {url}")
                status = CrawlStatus.ERROR
            except httpx.RequestError as e:
                log.warning(f"[{tool.id}] Erro de requisição: {url} — {e}")
                status = CrawlStatus.ERROR

            db.save_crawl(
                CrawlRecord(
                    tool_id=tool.id,
                    seed_url=seed_url,
                    discovered_url=url,
                    parent_url=parent_url,
                    crawl_depth=depth,
                    robots_allowed=True,
                    http_status=http_status,
                    content_type=content_type,
                    crawled_at=datetime.now(),
                    crawl_status=status,
                )
            )

            # Se a página foi acessada, descobrir novos links
            if html and depth < CRAWL_MAX_DEPTH:
                new_links = _extract_links(html, url, tool)
                for link in new_links:
                    if link not in visited:
                        queue.append((link, depth + 1, url, seed_url))

            # Delay respeitoso entre requisições
            time.sleep(CRAWL_DELAY_SECONDS)

    log.info(
        f"[{tool.id}] Crawling concluído. "
        f"Páginas acessíveis: {len(discovered_urls)}"
    )
    return discovered_urls
