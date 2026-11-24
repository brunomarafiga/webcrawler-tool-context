# Histórico de Alterações — Pipeline tool_context

## [2026-11-03] — Implementação inicial

### Arquivos criados

| Arquivo | Descrição |
|---|---|
| `pyproject.toml` | Configuração do projeto e dependências Python (uv/pip) |
| `.env.example` | Template para configuração da API key do Gemini |
| `config.py` | Configurações centralizadas (paths, delays, limites, modelo LLM) |
| `models.py` | Dataclasses tipadas e enums de status para todo o pipeline |
| `database.py` | Wrapper SQLite com 3 tabelas auxiliares de auditoria |
| `utils.py` | Utilitários compartilhados: logging, classificação de URL, filtros |
| `loader.py` | Leitura do Excel de entrada → lista de `Tool` objects |
| `crawler.py` | Web Crawler com controle de profundidade e respeito a robots.txt |
| `scraper.py` | Web Scraper (trafilatura + fallback BeautifulSoup) |
| `evidence_organizer.py` | Classificação das evidências nos 5 elementos do protocolo via Gemini |
| `generator.py` | Geração do parágrafo tool_context via Gemini (600–900 chars) |
| `validator.py` | Validação automática: tamanho, parágrafo único |
| `publisher.py` | Escrita dos resultados em nova planilha Excel com aba de status |
| `main.py` | Orquestrador principal com CLI e controle incremental |
| `data/` | Diretório para o banco SQLite (`pipeline.db`) |
| `output/` | Diretório para a planilha de saída |
| `logs/` | Diretório para o arquivo de log |

### Campos de saída
- **Único campo alterado**: `tool_context` (coluna F)
- **Planilha original**: preservada intacta
- **Planilha de saída**: `output/dataset-ferramentas-final.xlsx`

### Tecnologias utilizadas
- `httpx` — HTTP client com suporte a redirects
- `beautifulsoup4` + `lxml` — Parsing HTML
- `trafilatura` — Extração de conteúdo editorial
- `google-genai` — Gemini API (organização + geração)
- `tenacity` — Retry com backoff
- `openpyxl` — Leitura/escrita Excel
- `python-dotenv` — Variáveis de ambiente

---

## [2026-11-03] — Documentação e Isolamento de Ambiente sem Contêineres

### Arquivos adicionados

| Arquivo | Descrição |
|---|---|
| `README.md` | Documentação técnica completa do projeto, guia de instalação, arquitetura, manual de uso da CLI e critérios de curadoria |
| `.python-version` | Fixação estrita da versão do interpretador Python (`3.12`) para interoperabilidade com `uv` e `pyenv` |
| `.envrc.example` | Configuração padrão de isolamento estrito de variáveis de ambiente e ativação automática via `direnv` |
| `.gitignore` | Regras de exclusão de arquivos transitórios, logs, bancos locais, `.venv` e segredos |

---

## [2026-11-03] — Criação e Publicação do Repositório Git/GitHub

### Ações realizadas

- Inicialização do controle de versão local Git na branch `main`.
- Criação do repositório remoto privado no GitHub via GitHub CLI (`gh`):
  - **Repositório**: `brunomarafiga/webcrawler-tool-context`
  - **Visibilidade**: Privado (`isPrivate: true`)
  - **URL**: `https://github.com/brunomarafiga/webcrawler-tool-context`
- Publicação do commit inicial com os arquivos de código-fonte, configurações e documentação técnica.

---

## [2026-11-24] — Integração Ollama (Qwen 2.5), Suporte ao uv e Unificação de Branches

### Modificações e Melhorias
- **Cliente unificado de LLM (`llm_client.py`)**: Implementação de interface única para Ollama (Qwen 2.5 local) e Google Gemini.
- **Isolamento e execução via uv**: Adicionado suporte nativo e documentação para execução otimizada com `uv run --no-sync` ao lado do Poetry.
- **Correção de encoding UTF-8 no Windows (`utils.py`)**: Reconfiguração do stdout para evitar erros com caracteres Unicode em terminais Windows.
- **Atualização da documentação (`README.md`)**: Inclusão de guia completo para execução com uv, monitoramento de logs em tempo real (`Get-Content -Wait`) e arquitetura de resiliência transacional do SQLite.
- **Unificação de branches**: Fusão e sincronização da branch `feature/ollama-qwen` com a branch `main`.




