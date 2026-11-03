"""
Gerador de texto: redige o parágrafo tool_context a partir das evidências organizadas.

Usa o Gemini para produzir um único parágrafo em português de 600–900 caracteres,
com os 5 elementos do protocolo de curadoria na ordem obrigatória.
Faz até MAX_GENERATION_RETRIES tentativas, ajustando por extensão quando necessário.
"""

from __future__ import annotations

import logging

from config import (
    CONTEXT_MAX_CHARS,
    CONTEXT_MIN_CHARS,
    MAX_GENERATION_RETRIES,
)
from llm_client import LLMClient
from models import ContextElement, ELEMENT_ORDER, Tool

log = logging.getLogger("pipeline.generator")

GENERATION_PROMPT = """Você é um redator técnico especializado em documentação de ferramentas de software e inteligência artificial.

Redija um ÚNICO parágrafo em português claro e tecnicamente preciso sobre a ferramenta "{tool_name}".

REGRAS OBRIGATÓRIAS:
1. O parágrafo deve ter entre {min_chars} e {max_chars} caracteres (incluindo espaços). Este requisito é crítico.
2. Apresente os 5 elementos OBRIGATORIAMENTE NESTA ORDEM:
   a) FUNCIONAMENTO: o que a ferramenta faz e como funciona
   b) ENTRADA E SAÍDA: dados que recebe e resultados que produz
   c) TAREFAS ATENDIDAS: situações e casos de uso
   d) REQUISITOS: conta, instalação, configuração, integração, linguagem de programação necessária
   e) DIFERENCIAIS E LIMITAÇÕES: características distintivas e limitações documentadas
3. Use SOMENTE as evidências fornecidas abaixo. Não invente informações.
4. Descreva fatos verificáveis; não recomende nem emita juízos de valor.
5. Evite slogans, adjetivos promocionais e alegações de superioridade.
6. Mencione limitações apenas se houver evidência suficiente.
7. Não repita desnecessariamente o nome da ferramenta.
8. Escreva em português do Brasil, sem abreviações excessivas.

EVIDÊNCIAS POR ELEMENTO:
{evidences_text}

Responda APENAS com o parágrafo, sem títulos, listas, formatação markdown ou texto adicional."""

ADJUSTMENT_PROMPT_SHORT = """O parágrafo gerado tem {char_count} caracteres, menos que o mínimo de {min_chars}.
Expanda o texto adicionando mais detalhes dos elementos com base nas evidências fornecidas.
Mantenha-o como parágrafo único e respeite o limite máximo de {max_chars} caracteres.

Parágrafo atual:
{current_text}

Evidências disponíveis:
{evidences_text}

Responda APENAS com o novo parágrafo expandido."""

ADJUSTMENT_PROMPT_LONG = """O parágrafo gerado tem {char_count} caracteres, mais que o máximo de {max_chars}.
Reduza o texto mantendo os 5 elementos obrigatórios e as informações mais relevantes.
Mantenha-o como parágrafo único e respeite o mínimo de {min_chars} caracteres.

Parágrafo atual:
{current_text}

Responda APENAS com o novo parágrafo reduzido."""


def _format_evidences(organized: dict[ContextElement, str]) -> str:
    """Formata as evidências para inclusão no prompt."""
    labels = {
        ContextElement.FUNCIONAMENTO: "FUNCIONAMENTO",
        ContextElement.ENTRADA_SAIDA: "ENTRADA E SAÍDA",
        ContextElement.TAREFAS: "TAREFAS ATENDIDAS",
        ContextElement.REQUISITOS: "REQUISITOS",
        ContextElement.DIFERENCIAIS: "DIFERENCIAIS E LIMITAÇÕES",
    }
    parts: list[str] = []
    for el in ELEMENT_ORDER:
        evidence = organized.get(el, "")
        label = labels[el]
        if evidence:
            parts.append(f"[{label}]\n{evidence}")
        else:
            parts.append(f"[{label}]\n(sem evidência suficiente encontrada)")
    return "\n\n".join(parts)


def generate_context(
    tool: Tool,
    organized: dict[ContextElement, str],
    client: LLMClient,
) -> tuple[str, bool]:
    """
    Gera o tool_context para uma ferramenta.

    Returns:
        (texto_gerado, is_valid) — is_valid é True se o texto
        estiver dentro do intervalo de 600–900 caracteres.
    """
    evidences_text = _format_evidences(organized)
    current_text = ""

    for attempt in range(1, MAX_GENERATION_RETRIES + 1):
        log.debug(f"[{tool.id}] Tentativa {attempt}/{MAX_GENERATION_RETRIES}")

        try:
            if attempt == 1:
                # Primeira tentativa: geração inicial
                prompt = GENERATION_PROMPT.format(
                    tool_name=tool.name,
                    min_chars=CONTEXT_MIN_CHARS,
                    max_chars=CONTEXT_MAX_CHARS,
                    evidences_text=evidences_text,
                )
            elif len(current_text) < CONTEXT_MIN_CHARS:
                # Texto muito curto: expandir
                prompt = ADJUSTMENT_PROMPT_SHORT.format(
                    char_count=len(current_text),
                    min_chars=CONTEXT_MIN_CHARS,
                    max_chars=CONTEXT_MAX_CHARS,
                    current_text=current_text,
                    evidences_text=evidences_text,
                )
            else:
                # Texto muito longo: reduzir
                prompt = ADJUSTMENT_PROMPT_LONG.format(
                    char_count=len(current_text),
                    min_chars=CONTEXT_MIN_CHARS,
                    max_chars=CONTEXT_MAX_CHARS,
                    current_text=current_text,
                )

            current_text = client.generate(prompt, temperature=0.3)
            char_count = len(current_text)

            log.debug(
                f"[{tool.id}] Tentativa {attempt}: {char_count} chars"
            )

            if CONTEXT_MIN_CHARS <= char_count <= CONTEXT_MAX_CHARS:
                log.info(
                    f"[{tool.id}] Context gerado com sucesso: "
                    f"{char_count} chars (tentativa {attempt})"
                )
                return current_text, True

        except Exception as e:
            log.error(f"[{tool.id}] Erro na geração (tentativa {attempt}): {e}")
            continue

    # Esgotou as tentativas — retorna o melhor resultado obtido
    char_count = len(current_text)
    log.warning(
        f"[{tool.id}] Geração fora do intervalo após {MAX_GENERATION_RETRIES} "
        f"tentativas: {char_count} chars"
    )
    return current_text, False
