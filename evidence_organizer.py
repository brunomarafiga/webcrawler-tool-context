"""
Organização de Evidências: classifica os trechos extraídos nos 5 elementos
obrigatórios do protocolo de curadoria usando o Gemini API.
"""

from __future__ import annotations

import json
import logging

from google import genai

from config import GEMINI_MODEL
from models import ContextElement, ELEMENT_ORDER, EvidenceRecord, Tool

log = logging.getLogger("pipeline.organizer")

# Descrição dos elementos para o prompt de classificação
ELEMENT_DESCRIPTIONS = {
    ContextElement.FUNCIONAMENTO: "O que a ferramenta faz e como funciona",
    ContextElement.ENTRADA_SAIDA: "Quais dados/conteúdos recebe e quais resultados produz",
    ContextElement.TAREFAS: "Tarefas e situações de uso em que pode ser utilizada",
    ContextElement.REQUISITOS: "Necessidade de conta, instalação, configuração, integração, programação",
    ContextElement.DIFERENCIAIS: "Características distintivas e limitações conhecidas e documentadas",
}

CLASSIFICATION_PROMPT = """Analise o conteúdo extraído sobre a ferramenta "{tool_name}" e classifique as informações nos 5 elementos abaixo.

Para cada elemento, extraia os trechos factuais e verificáveis mais relevantes do conteúdo fornecido.
Use APENAS informações presentes no conteúdo. Não invente nem complemente com conhecimento externo.

Elementos (responda com as chaves exatas):
- funcionamento: {desc_func}
- entrada_saida: {desc_io}
- tarefas: {desc_tasks}
- requisitos: {desc_reqs}
- diferenciais_limitacoes: {desc_diff}

Conteúdo extraído das fontes oficiais:
---
{content}
---

Responda SOMENTE com JSON no formato:
{{
  "funcionamento": "trecho(s) relevante(s) ou string vazia se não encontrado",
  "entrada_saida": "trecho(s) relevante(s) ou string vazia se não encontrado",
  "tarefas": "trecho(s) relevante(s) ou string vazia se não encontrado",
  "requisitos": "trecho(s) relevante(s) ou string vazia se não encontrado",
  "diferenciais_limitacoes": "trecho(s) relevante(s) ou string vazia se não encontrado"
}}"""


def _build_content_block(evidences: list[EvidenceRecord]) -> str:
    """Monta bloco de conteúdo a partir das evidências coletadas."""
    parts: list[str] = []
    for ev in evidences:
        if ev.extracted_text:
            # Limitar por evidência para não estourar contexto
            text_snippet = ev.extracted_text[:3000]
            parts.append(
                f"[Fonte: {ev.source_url} | Tipo: {ev.source_type}]\n"
                f"Título: {ev.page_title}\n"
                f"{text_snippet}"
            )
    return "\n\n---\n\n".join(parts)


def organize_evidence(
    tool: Tool,
    evidences: list[EvidenceRecord],
    client: genai.Client,
) -> dict[ContextElement, str]:
    """
    Classifica evidências nos 5 elementos obrigatórios via Gemini.

    Retorna dict mapeando cada ContextElement ao trecho de evidência encontrado
    (string vazia se não encontrado).
    """
    # Resultado padrão com elementos vazios
    result: dict[ContextElement, str] = {el: "" for el in ELEMENT_ORDER}

    if not evidences:
        log.warning(f"[{tool.id}] Sem evidências para organizar.")
        return result

    content_block = _build_content_block(evidences)
    if not content_block.strip():
        log.warning(f"[{tool.id}] Conteúdo extraído vazio.")
        return result

    prompt = CLASSIFICATION_PROMPT.format(
        tool_name=tool.name,
        desc_func=ELEMENT_DESCRIPTIONS[ContextElement.FUNCIONAMENTO],
        desc_io=ELEMENT_DESCRIPTIONS[ContextElement.ENTRADA_SAIDA],
        desc_tasks=ELEMENT_DESCRIPTIONS[ContextElement.TAREFAS],
        desc_reqs=ELEMENT_DESCRIPTIONS[ContextElement.REQUISITOS],
        desc_diff=ELEMENT_DESCRIPTIONS[ContextElement.DIFERENCIAIS],
        content=content_block,
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = response.text.strip()

        # Remover blocos de markdown se presentes
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed: dict[str, str] = json.loads(raw)

        for element in ELEMENT_ORDER:
            value = parsed.get(element.value, "")
            result[element] = str(value).strip() if value else ""

        filled = sum(1 for v in result.values() if v)
        log.info(
            f"[{tool.id}] Evidências organizadas. "
            f"Elementos preenchidos: {filled}/5"
        )
    except json.JSONDecodeError as e:
        log.error(f"[{tool.id}] Erro ao parsear JSON da organização: {e}")
    except Exception as e:
        log.error(f"[{tool.id}] Erro na organização de evidências: {e}")

    return result
