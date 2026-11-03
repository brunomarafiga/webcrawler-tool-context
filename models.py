"""
Modelos de dados (dataclasses) utilizados em todo o pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums de status
# ---------------------------------------------------------------------------


class CrawlStatus(str, Enum):
    PENDING = "pendente"
    COMPLETED = "concluido"
    SKIPPED = "ignorado"
    ERROR = "erro"


class ScrapeStatus(str, Enum):
    COMPLETED = "concluido"
    PARTIAL = "parcial"
    SKIPPED = "ignorado"
    FAILED = "falhou"


class ToolStatus(str, Enum):
    APPROVED = "aprovado"
    PENDING_REVIEW = "pendente_revisao"
    FAILED = "falha_tecnica"
    NOT_PROCESSED = "nao_processado"


class ContextElement(str, Enum):
    FUNCIONAMENTO = "funcionamento"
    ENTRADA_SAIDA = "entrada_saida"
    TAREFAS = "tarefas"
    REQUISITOS = "requisitos"
    DIFERENCIAIS = "diferenciais_limitacoes"


# Ordem canônica dos elementos — deve ser respeitada na geração
ELEMENT_ORDER: list[ContextElement] = [
    ContextElement.FUNCIONAMENTO,
    ContextElement.ENTRADA_SAIDA,
    ContextElement.TAREFAS,
    ContextElement.REQUISITOS,
    ContextElement.DIFERENCIAIS,
]


# ---------------------------------------------------------------------------
# Modelos de domínio
# ---------------------------------------------------------------------------


@dataclass
class Tool:
    """Representa uma ferramenta de IA cadastrada na base."""

    id: int
    name: str
    official_link: str
    documentation_link: str
    repository_link: str
    tool_context: str = ""

    def seed_urls(self) -> list[str]:
        """Retorna URLs seed não-vazias e únicas, na ordem de prioridade."""
        seen: set[str] = set()
        result: list[str] = []
        for url in [self.official_link, self.documentation_link, self.repository_link]:
            url = (url or "").strip()
            if url and url not in seen:
                seen.add(url)
                result.append(url)
        return result


@dataclass
class CrawlRecord:
    """Log de uma página descoberta pelo crawler."""

    tool_id: int
    seed_url: str
    discovered_url: str
    parent_url: str
    crawl_depth: int
    robots_allowed: bool
    http_status: int | None
    content_type: str
    crawled_at: datetime
    crawl_status: CrawlStatus


@dataclass
class EvidenceRecord:
    """Trecho de conteúdo extraído de uma página."""

    tool_id: int
    source_url: str
    source_type: str
    page_title: str
    extracted_text: str
    extraction_method: str
    extracted_at: datetime
    scrape_status: ScrapeStatus
    content_hash: str
    context_element: ContextElement | None
    evidence_excerpt: str


@dataclass
class ValidationResult:
    """Resultado da validação de conformidade de um tool_context."""

    tool_id: int
    char_count: int
    chars_ok: bool
    has_single_paragraph: bool
    status: ToolStatus
    issues: list[str] = field(default_factory=list)
