"""
Loader: lê o dataset Excel e retorna a lista de Tool objects.
"""

from __future__ import annotations

import logging
from pathlib import Path

import openpyxl

from config import INPUT_EXCEL
from models import Tool

log = logging.getLogger("pipeline.loader")


def load_tools(excel_path: Path = INPUT_EXCEL) -> list[Tool]:
    """Lê a planilha e retorna todas as ferramentas cadastradas."""
    log.info(f"Carregando ferramentas de: {excel_path}")
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active

    tools: list[Tool] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Colunas: ID, tool_name, official_link, docs_link, repo_link, tool_context
        if not row[0]:
            continue
        try:
            tool = Tool(
                id=int(float(row[0])),
                name=str(row[1] or "").strip(),
                official_link=str(row[2] or "").strip(),
                documentation_link=str(row[3] or "").strip(),
                repository_link=str(row[4] or "").strip(),
                tool_context=str(row[5] or "").strip() if len(row) > 5 else "",
            )
            tools.append(tool)
        except (ValueError, TypeError) as e:
            log.warning(f"Linha ignorada (ID={row[0]}): {e}")

    wb.close()
    log.info(f"{len(tools)} ferramentas carregadas.")
    return tools
