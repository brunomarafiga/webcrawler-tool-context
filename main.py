"""
Orquestrador principal do pipeline de extração do tool_context.

Uso:
    python main.py                    # Processa todas as ferramentas
    python main.py --limit 5          # Processa apenas as 5 primeiras
    python main.py --tool-id 42       # Processa apenas a ferramenta ID=42
    python main.py --dry-run          # Simula sem chamar o LLM
    python main.py --reprocess        # Reprocessa mesmo os já aprovados
    python main.py --publish-only     # Apenas gera o Excel de saída
    python main.py --report           # Exibe resumo do banco de dados
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    MIN_ELEMENTS_WITH_EVIDENCE,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)
from crawler import crawl_tool
from database import Database
from evidence_organizer import organize_evidence
from generator import generate_context
from llm_client import LLMClient, create_llm_client
from loader import load_tools
from models import ContextElement, Tool, ToolStatus
from publisher import publish_results
from scraper import scrape_urls
from utils import setup_logging
from validator import validate_context

log = logging.getLogger("pipeline")


def _count_elements_with_evidence(organized: dict[ContextElement, str]) -> int:
    return sum(1 for v in organized.values() if v.strip())


def process_tool(
    tool: Tool,
    db: Database,
    llm_client: LLMClient | None,
    dry_run: bool = False,
) -> ToolStatus:
    """Pipeline completo para uma ferramenta. Retorna o status final."""

    log.info(f"[{tool.id}] ▶ Iniciando: {tool.name}")
    start = time.time()

    # -------------------------------------------------------------------
    # Etapa 1: Web Crawling
    # -------------------------------------------------------------------
    urls = crawl_tool(tool, db)
    if not urls:
        log.warning(f"[{tool.id}] Nenhuma URL acessível encontrada.")
        # Registrar falha e retornar
        from models import ValidationResult
        db.save_generation(
            tool.id,
            "",
            ValidationResult(
                tool_id=tool.id,
                char_count=0,
                chars_ok=False,
                has_single_paragraph=False,
                status=ToolStatus.FAILED,
                issues=["Nenhuma URL acessível encontrada pelo crawler."],
            ),
        )
        return ToolStatus.FAILED

    # -------------------------------------------------------------------
    # Etapa 2: Web Scraping
    # -------------------------------------------------------------------
    evidences = scrape_urls(urls, tool.id, db)
    if not evidences:
        log.warning(f"[{tool.id}] Nenhum conteúdo extraído das páginas.")
        from models import ValidationResult
        db.save_generation(
            tool.id,
            "",
            ValidationResult(
                tool_id=tool.id,
                char_count=0,
                chars_ok=False,
                has_single_paragraph=False,
                status=ToolStatus.FAILED,
                issues=["Nenhum conteúdo textual extraído das páginas."],
            ),
        )
        return ToolStatus.FAILED

    if dry_run or llm_client is None:
        log.info(f"[{tool.id}] [DRY-RUN] Pulando geração LLM.")
        return ToolStatus.NOT_PROCESSED

    # -------------------------------------------------------------------
    # Etapa 3: Organização de evidências
    # -------------------------------------------------------------------
    organized = organize_evidence(tool, evidences, llm_client)

    filled = _count_elements_with_evidence(organized)
    if filled < MIN_ELEMENTS_WITH_EVIDENCE:
        log.warning(
            f"[{tool.id}] Evidências insuficientes: {filled}/5 elementos preenchidos. "
            f"Encaminhando para revisão humana."
        )
        from models import ValidationResult
        db.save_generation(
            tool.id,
            "",
            ValidationResult(
                tool_id=tool.id,
                char_count=0,
                chars_ok=False,
                has_single_paragraph=False,
                status=ToolStatus.PENDING_REVIEW,
                issues=[
                    f"Evidências insuficientes: apenas {filled}/5 elementos cobertos."
                ],
            ),
        )
        return ToolStatus.PENDING_REVIEW

    # -------------------------------------------------------------------
    # Etapa 4: Geração do texto
    # -------------------------------------------------------------------
    text, is_valid = generate_context(tool, organized, llm_client)

    # -------------------------------------------------------------------
    # Etapa 5: Validação
    # -------------------------------------------------------------------
    validation = validate_context(tool.id, text)
    db.save_generation(tool.id, text, validation)

    elapsed = time.time() - start
    log.info(
        f"[{tool.id}] ■ Concluído em {elapsed:.1f}s — "
        f"Status: {validation.status.value} | "
        f"Chars: {validation.char_count}"
    )

    if validation.status == ToolStatus.APPROVED:
        tool.tool_context = text

    return validation.status


def run_pipeline(args: argparse.Namespace) -> None:
    """Executa o pipeline conforme os argumentos fornecidos."""
    setup_logging(verbose=args.verbose)

    db = Database()

    # Modo relatório
    if args.report:
        summary = db.summary()
        print("\n=== Resumo do Pipeline ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        return

    # Carregar ferramentas
    tools = load_tools()

    # Filtros
    if args.tool_id:
        tools = [t for t in tools if t.id == args.tool_id]
        if not tools:
            log.error(f"Ferramenta com ID={args.tool_id} não encontrada.")
            sys.exit(1)
    if args.limit:
        tools = tools[: args.limit]

    log.info(
        f"Pipeline iniciado — {len(tools)} ferramenta(s) a processar. "
        f"Provedor: {LLM_PROVIDER} | Modelo: "
        f"{OLLAMA_MODEL if LLM_PROVIDER == 'ollama' else GEMINI_MODEL}"
    )

    # Modo publish-only
    if args.publish_only:
        log.info("Modo publish-only: gerando planilha de saída.")
        # Recuperar tool_context aprovados do banco
        for tool in tools:
            approved = db.get_approved_text(tool.id)
            if approved:
                tool.tool_context = approved
        publish_results(tools, db)
        return

    # Inicializar o provedor LLM selecionado
    llm_client: LLMClient | None = None
    if not args.dry_run:
        try:
            llm_client = create_llm_client(
                LLM_PROVIDER,
                gemini_api_key=GEMINI_API_KEY,
                gemini_model=GEMINI_MODEL,
                ollama_host=OLLAMA_HOST,
                ollama_model=OLLAMA_MODEL,
                ollama_timeout=OLLAMA_TIMEOUT_SECONDS,
            )
        except ValueError as exc:
            log.error(str(exc))
            sys.exit(1)

    # Processar ferramentas
    stats = {s: 0 for s in ToolStatus}

    for tool in tools:
        # Pular já aprovados (a não ser que --reprocess seja passado)
        if not args.reprocess and db.is_approved(tool.id):
            log.info(f"[{tool.id}] Já aprovado — pulando. (use --reprocess para forçar)")
            approved = db.get_approved_text(tool.id)
            if approved:
                tool.tool_context = approved
            stats[ToolStatus.APPROVED] += 1
            continue

        status = process_tool(tool, db, llm_client, dry_run=args.dry_run)
        stats[status] += 1

    # Publicar resultados
    if not args.dry_run:
        publish_results(tools, db)

    # Resumo final
    log.info("\n=== Resultado Final ===")
    for status, count in stats.items():
        if count:
            log.info(f"  {status.value}: {count}")

    db_summary = db.summary()
    log.info(f"\n=== Banco de Dados ===")
    for k, v in db_summary.items():
        log.info(f"  {k}: {v}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline de extração do campo tool_context."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Processar apenas as N primeiras ferramentas.",
    )
    parser.add_argument(
        "--tool-id",
        type=int,
        default=None,
        metavar="ID",
        help="Processar apenas a ferramenta com este ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executar crawling e scraping sem chamar o LLM.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocessar ferramentas já aprovadas.",
    )
    parser.add_argument(
        "--publish-only",
        action="store_true",
        help="Apenas gerar a planilha de saída a partir do banco.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Exibir resumo do banco de dados e sair.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Logging detalhado (DEBUG).",
    )
    return parser


if __name__ == "__main__":
    parser = build_arg_parser()
    args = parser.parse_args()
    run_pipeline(args)
