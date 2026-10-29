# T1 · Análise do TamAGI e proveniência

## Inspeção realizada

Repositório: <https://github.com/manikmakki/TamAGI>, branch `main`, commit inspecionado **`b3bb5b1e0ee0808e5e928d4ab3d563af42e0fdd6`** (commit de 09/07/2026). Foram examinados `README.md`, `LICENSE.md`, `pyproject.toml`, `requirements.txt`, os módulos `backend/core/personality.py`, `memory.py`, `world_thread.py`, `consolidation.py`, `agent.py`, `main.py`, rotas em `backend/api`, `frontend/index.html`, documentação e árvore de testes. Esta análise descreve esse snapshot; a branch remota pode mudar.

| Tema | Documentado | Código inspecionado / ressalva |
|---|---|---|
| Personalidade e humor | README menciona humor, energia e XP. | `TamAGIState` contém `vitality` e `curiosity`. Humor para pose depende apenas de vitalidade: ≥75 happy, ≥55 content, ≥35 neutral, abaixo tired. O frontend exibe vitalidade/curiosidade. |
| XP e evolução | Crescimento e níveis. | `level = 1 + experience // 50`; índice de estágio `min(experience // 250, 39)` (40 estágios). XP de mensagem 1, skill 3, memória 2, criação de skill 10 e conhecimento 5. O agente nomeia novos estágios com LLM e tem fallback. **Não são os números deste módulo.** |
| Tempo e interação | O README sugere tristeza por negligência. | Código reduz vitalidade 0,5 e curiosidade 3 por mensagem; após 15 min de inatividade, vitalidade deriva até um alvo conforme hora, até 15 pontos/h; curiosidade sobe de 2 a 5 pontos/h conforme estágio. O módulo SL-001 não copia a punição por ausência. |
| Persistência | ChromaDB; README cita Elasticsearch. | Personalidade em `data/tamagi_state.json`; memória possui `chromadb.PersistentClient` e fallback em memória se ChromaDB não estiver instalado; há backend Elasticsearch separado. Não foi necessário instalar nenhum deles. |
| Autonomia | README ainda descreve Dream/Explore/Experiment/Journal e `/api/dreams/*`. | `backend/main.py` inicializa `WorldThread`; `backend/core/world_thread.py` diz expressamente que ele **substitui** Dream/Motivation Engines, com cron, LLM e skills. Não foram encontradas as rotas `/api/dreams/*` ou uma classe DreamEngine ativa no snapshot. Não se deve apresentar o README antigo como implementação atual. |
| API e interface | PWA, REST, WebSocket, canvas e editor. | Rotas FastAPI REST e `/api/ws` existem; `frontend/index.html` usa canvas/skeleton e WebSocket, e existe editor de sprites. São recursos do TamAGI, não do Muse F8. |
| Testes | Não há suíte descrita como evidência. | Nenhuma árvore `tests/`, arquivo `test_*` ou `*_test.*` foi encontrada na inspeção. Isso não prova que o projeto nunca seja testado por outros meios. |
| Dependências | Python/FastAPI, LLM, ChromaDB, MCP. | `requirements.txt` também inclui Elasticsearch, embeddings, MCP, keyring, croniter e outras bibliotecas; `pyproject.toml` lista um subconjunto. Este protótipo executa só com a biblioteca padrão Python. |

## Licença e decisões

O repositório declara **GNU AGPL-3.0**, e `pyproject.toml` indica `AGPL-3.0-only`. A reutilização direta de código protegido pode exigir preservação de avisos, licença e disponibilização do código-fonte correspondente ao distribuir uma obra derivada; modificações disponibilizadas por rede podem acionar as exigências do §13. Os efeitos concretos sobre um produto e sua arquitetura devem ser avaliados por assessoria jurídica antes de qualquer cópia, adaptação ou distribuição. Esta nota não é parecer jurídico.

**Nenhum código, componente, sprite ou asset do TamAGI foi incorporado.** Ideias gerais examinadas: estado persistente, humor derivado, progressão, memória de eventos, atividades locais e interface de convivência. Fórmulas, implementação, conteúdo, UI e limites aqui são próprios/decorrentes da especificação do usuário. O fundo ambiental foi gerado especificamente para este protótipo, sem personagem, não extraído do TamAGI. O vídeo de teste é um padrão de cores gerado localmente; não é o SL-001. Nenhuma licença de distribuição comercial do produto foi presumida.
