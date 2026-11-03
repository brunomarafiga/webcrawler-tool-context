"""
Validador: verifica conformidade do tool_context gerado com o protocolo.
Checagens: tamanho (600-900 chars), parágrafo único, conteúdo não vazio.
"""

from __future__ import annotations

import logging

from config import CONTEXT_MAX_CHARS, CONTEXT_MIN_CHARS
from models import ToolStatus, ValidationResult

log = logging.getLogger("pipeline.validator")


def validate_context(tool_id: int, text: str) -> ValidationResult:
    """
    Valida o tool_context gerado contra os critérios do protocolo.

    Critérios:
    1. Texto não vazio
    2. Entre 600 e 900 caracteres (incluindo espaços)
    3. Parágrafo único (sem quebras duplas de linha)
    """
    issues: list[str] = []

    # 1. Conteúdo não vazio
    if not text or not text.strip():
        return ValidationResult(
            tool_id=tool_id,
            char_count=0,
            chars_ok=False,
            has_single_paragraph=False,
            status=ToolStatus.FAILED,
            issues=["Texto gerado está vazio."],
        )

    text = text.strip()
    char_count = len(text)

    # 2. Contagem de caracteres
    chars_ok = CONTEXT_MIN_CHARS <= char_count <= CONTEXT_MAX_CHARS
    if not chars_ok:
        if char_count < CONTEXT_MIN_CHARS:
            issues.append(
                f"Texto muito curto: {char_count} chars "
                f"(mínimo: {CONTEXT_MIN_CHARS})"
            )
        else:
            issues.append(
                f"Texto muito longo: {char_count} chars "
                f"(máximo: {CONTEXT_MAX_CHARS})"
            )

    # 3. Parágrafo único — sem linhas em branco duplas
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    has_single_paragraph = len(paragraphs) <= 1
    if not has_single_paragraph:
        issues.append(
            f"Múltiplos parágrafos detectados: {len(paragraphs)} blocos."
        )

    # Determinar status
    if chars_ok and has_single_paragraph:
        status = ToolStatus.APPROVED
    else:
        status = ToolStatus.PENDING_REVIEW

    result = ValidationResult(
        tool_id=tool_id,
        char_count=char_count,
        chars_ok=chars_ok,
        has_single_paragraph=has_single_paragraph,
        status=status,
        issues=issues,
    )

    if issues:
        log.debug(
            f"[{tool_id}] Validação com problemas: {issues}"
        )
    else:
        log.debug(f"[{tool_id}] Validação aprovada: {char_count} chars")

    return result
