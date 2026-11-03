"""
Publisher: escreve os tool_context aprovados em uma nova planilha Excel.
Preserva a planilha original intacta. Gera uma aba de status com o resumo.
"""

from __future__ import annotations

import logging
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config import INPUT_EXCEL, OUTPUT_DIR, OUTPUT_EXCEL
from database import Database
from models import Tool, ToolStatus

log = logging.getLogger("pipeline.publisher")

# Cores para status na aba de relatório
COLOR_APPROVED = "C6EFCE"   # Verde claro
COLOR_PENDING = "FFEB9C"    # Amarelo
COLOR_FAILED = "FFC7CE"     # Vermelho claro
COLOR_NOT_PROCESSED = "D9D9D9"  # Cinza


def publish_results(
    tools: list[Tool],
    db: Database,
    output_path: Path = OUTPUT_EXCEL,
) -> None:
    """
    Gera a planilha de saída com os tool_context preenchidos.
    - Aba principal: cópia do original com tool_context atualizado
    - Aba '_status': relatório de status por ferramenta
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Gerando planilha de saída: {output_path}")

    # Carregar planilha original como base
    wb = openpyxl.load_workbook(INPUT_EXCEL)
    ws_main = wb.active

    # Mapear tools por ID para lookup rápido
    tools_by_id = {t.id: t for t in tools}

    # Preencher tool_context na aba principal (coluna F = índice 6)
    approved_count = 0
    for row in ws_main.iter_rows(min_row=2, max_row=ws_main.max_row):
        cell_id = row[0]
        if cell_id.value is None:
            continue
        try:
            tool_id = int(float(cell_id.value))
        except (ValueError, TypeError):
            continue

        tool = tools_by_id.get(tool_id)
        if tool and tool.tool_context:
            row[5].value = tool.tool_context  # Coluna F (índice 5)
            approved_count += 1

    log.info(f"tool_context preenchido para {approved_count} ferramentas.")

    # ------------------------------------------------------------------
    # Aba de status
    # ------------------------------------------------------------------
    if "_status" in wb.sheetnames:
        del wb["_status"]

    ws_status = wb.create_sheet("_status")

    # Cabeçalho
    headers = [
        "ID", "tool_name", "status", "char_count", "issues",
        "tool_context (prévia 100 chars)"
    ]
    for col_idx, header in enumerate(headers, 1):
        cell = ws_status.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(fill_type="solid", fgColor="4472C4")
        cell.font = Font(bold=True, color="FFFFFF")

    # Coletar logs de geração do banco
    summary = db.summary()

    for row_idx, tool in enumerate(tools, 2):
        approved_text = db.get_approved_text(tool.id)

        # Determinar status efetivo
        if approved_text:
            status_label = "aprovado"
            char_count = len(approved_text)
            issues = ""
            fill_color = COLOR_APPROVED
            preview = approved_text[:100] + "..." if len(approved_text) > 100 else approved_text
        elif tool.tool_context:
            # Texto existe mas não aprovado formalmente
            status_label = "pendente_revisao"
            char_count = len(tool.tool_context)
            issues = "Verificar manualmente"
            fill_color = COLOR_PENDING
            preview = tool.tool_context[:100]
        else:
            status_label = "nao_processado"
            char_count = 0
            issues = ""
            fill_color = COLOR_NOT_PROCESSED
            preview = ""

        row_data = [tool.id, tool.name, status_label, char_count, issues, preview]
        for col_idx, value in enumerate(row_data, 1):
            cell = ws_status.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = PatternFill(fill_type="solid", fgColor=fill_color)
            cell.alignment = Alignment(wrap_text=False)

    # Ajustar larguras
    col_widths = [8, 30, 20, 12, 40, 60]
    for i, width in enumerate(col_widths, 1):
        ws_status.column_dimensions[get_column_letter(i)].width = width

    wb.save(output_path)
    log.info(
        f"Planilha salva: {output_path}\n"
        f"Resumo: {summary}"
    )
