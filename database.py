"""
Banco de dados SQLite para controle operacional e auditoria do pipeline.
Armazena registros de crawling, evidências extraídas e logs de geração.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config import DB_PATH
from models import (
    ContextElement,
    CrawlRecord,
    CrawlStatus,
    EvidenceRecord,
    ScrapeStatus,
    ToolStatus,
    ValidationResult,
)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS crawl_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id          INTEGER NOT NULL,
    seed_url         TEXT,
    discovered_url   TEXT NOT NULL,
    parent_url       TEXT,
    crawl_depth      INTEGER DEFAULT 0,
    robots_allowed   BOOLEAN DEFAULT 1,
    http_status      INTEGER,
    content_type     TEXT,
    crawled_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    crawl_status     TEXT DEFAULT 'pendente'
);

CREATE TABLE IF NOT EXISTS scrape_evidence (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id           INTEGER NOT NULL,
    source_url        TEXT NOT NULL,
    source_type       TEXT,
    page_title        TEXT,
    extracted_text    TEXT,
    extraction_method TEXT,
    extracted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scrape_status     TEXT DEFAULT 'pendente',
    content_hash      TEXT,
    context_element   TEXT,
    evidence_excerpt  TEXT
);

CREATE TABLE IF NOT EXISTS generation_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id        INTEGER NOT NULL,
    generated_text TEXT,
    char_count     INTEGER,
    attempt_number INTEGER,
    status         TEXT DEFAULT 'nao_processado',
    issues         TEXT,
    generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crawl_tool ON crawl_log(tool_id);
CREATE INDEX IF NOT EXISTS idx_evidence_tool ON scrape_evidence(tool_id);
CREATE INDEX IF NOT EXISTS idx_generation_tool ON generation_log(tool_id);
"""


class Database:
    """Wrapper SQLite para as tabelas auxiliares do pipeline."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------
    # Crawl log
    # ------------------------------------------------------------------

    def save_crawl(self, record: CrawlRecord) -> None:
        sql = """
            INSERT INTO crawl_log
            (tool_id, seed_url, discovered_url, parent_url, crawl_depth,
             robots_allowed, http_status, content_type, crawled_at, crawl_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._conn() as conn:
            conn.execute(
                sql,
                (
                    record.tool_id,
                    record.seed_url,
                    record.discovered_url,
                    record.parent_url,
                    record.crawl_depth,
                    int(record.robots_allowed),
                    record.http_status,
                    record.content_type,
                    record.crawled_at.isoformat(),
                    record.crawl_status.value,
                ),
            )

    def get_crawled_urls(self, tool_id: int) -> list[str]:
        """Retorna URLs já crawleadas com sucesso para uma ferramenta."""
        sql = """
            SELECT discovered_url FROM crawl_log
            WHERE tool_id = ? AND crawl_status = 'concluido'
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (tool_id,)).fetchall()
        return [r["discovered_url"] for r in rows]

    # ------------------------------------------------------------------
    # Evidências (scrape)
    # ------------------------------------------------------------------

    def save_evidence(self, record: EvidenceRecord) -> None:
        sql = """
            INSERT INTO scrape_evidence
            (tool_id, source_url, source_type, page_title, extracted_text,
             extraction_method, extracted_at, scrape_status, content_hash,
             context_element, evidence_excerpt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._conn() as conn:
            conn.execute(
                sql,
                (
                    record.tool_id,
                    record.source_url,
                    record.source_type,
                    record.page_title,
                    record.extracted_text,
                    record.extraction_method,
                    record.extracted_at.isoformat(),
                    record.scrape_status.value,
                    record.content_hash,
                    record.context_element.value if record.context_element else None,
                    record.evidence_excerpt,
                ),
            )

    def get_evidences(self, tool_id: int) -> list[dict]:
        sql = """
            SELECT * FROM scrape_evidence
            WHERE tool_id = ? AND scrape_status IN ('concluido', 'parcial')
            ORDER BY id
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (tool_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Log de geração
    # ------------------------------------------------------------------

    def save_generation(
        self,
        tool_id: int,
        text: str,
        result: ValidationResult,
        attempt: int = 1,
    ) -> None:
        sql = """
            INSERT INTO generation_log
            (tool_id, generated_text, char_count, attempt_number, status, issues, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._conn() as conn:
            conn.execute(
                sql,
                (
                    tool_id,
                    text,
                    result.char_count,
                    attempt,
                    result.status.value,
                    json.dumps(result.issues, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )

    # ------------------------------------------------------------------
    # Controle de reprocessamento
    # ------------------------------------------------------------------

    def is_approved(self, tool_id: int) -> bool:
        """Verifica se a ferramenta já tem um context aprovado."""
        sql = """
            SELECT 1 FROM generation_log
            WHERE tool_id = ? AND status = 'aprovado'
            LIMIT 1
        """
        with self._conn() as conn:
            row = conn.execute(sql, (tool_id,)).fetchone()
        return row is not None

    def get_approved_text(self, tool_id: int) -> str | None:
        sql = """
            SELECT generated_text FROM generation_log
            WHERE tool_id = ? AND status = 'aprovado'
            ORDER BY generated_at DESC
            LIMIT 1
        """
        with self._conn() as conn:
            row = conn.execute(sql, (tool_id,)).fetchone()
        return row["generated_text"] if row else None

    # ------------------------------------------------------------------
    # Relatório resumido
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        with self._conn() as conn:
            total_crawled = conn.execute(
                "SELECT COUNT(DISTINCT tool_id) FROM crawl_log"
            ).fetchone()[0]
            total_evidence = conn.execute(
                "SELECT COUNT(*) FROM scrape_evidence"
            ).fetchone()[0]
            approved = conn.execute(
                "SELECT COUNT(DISTINCT tool_id) FROM generation_log WHERE status='aprovado'"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(DISTINCT tool_id) FROM generation_log WHERE status='pendente_revisao'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(DISTINCT tool_id) FROM generation_log WHERE status='falha_tecnica'"
            ).fetchone()[0]
        return {
            "ferramentas_crawleadas": total_crawled,
            "evidencias_coletadas": total_evidence,
            "aprovados": approved,
            "pendentes_revisao": pending,
            "falhas": failed,
        }
