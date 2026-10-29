# Ponte Muse · contrato proposto 0.1

Não há importação das classes ou banco F1–F9, e a F9 real não estava disponível para inspeção. Os identificadores, a semântica e as transições devem ser conciliados com os contratos reais antes da integração. O contrato abaixo é testado com `tests/fixtures/muse_events.json`.

## Autenticação e consentimento do protótipo

O servidor HTTP aceita somente conexões em `127.0.0.1`/`localhost` e rejeita bind público, LAN ou proxy. Ele gera dois tokens aleatórios independentes (256 bits) por execução: proprietário e ponte, em arquivos privados cujos caminhos aparecem no terminal. Nunca envie o conteúdo dos arquivos para o chat, URL, logs, Git ou backups. O processo que usa a ponte deve ler seu token privado e enviar `Authorization: Bearer <token>` em HTTP **somente para localhost**. O dono usa o token de proprietário para desbloquear a interface ou para chamadas administrativas locais; o token da ponte não tem privilégios de proprietário, e a sessão do navegador não equivale ao token da ponte.

Em Configurações → Consentimento da ponte, ou no endpoint administrativo autenticado `POST /api/bridge/consent`, o proprietário define exatamente:

```json
{"receiveEvents": false, "shareData": false}
```

- `receiveEvents`: autoriza eventos de entrada e uma confirmação com `duplicate`, `duplicateKind` e `xpAwarded`; **não** exporta o estado completo.
- `shareData`: autoriza a leitura de contexto e histórico técnico de eventos. O histórico pode conter IDs; não use dados pessoais nesses IDs.

Ambos são `false` por padrão, podem ser revogados independentemente, expiram após 8 horas e são apagados ao reiniciar ou bloquear a sessão. A revogação serializa com operações já admitidas, mas não recolhe dados ou respostas que já saíram. A credencial não substitui o consentimento: sem token válido retorna 401; com token válido e escopo negado retorna 403. O endpoint administrativo exige credencial ou sessão do proprietário e não aceita o token da ponte. A interface local consulta `/api/ui/events` e `/api/ui/events/cursor` com sessão do proprietário; `/api/events` é exclusivo do cliente da ponte com consentimento de compartilhamento. O cursor da UI marca a fronteira do histórico existente na abertura e retorna apenas o maior número de sequência, não os eventos da ponte.

O servidor não emite cabeçalhos CORS de autorização, valida `Host` e `Origin`, ignora `X-Forwarded-*` e usa cookie de sessão `HttpOnly; SameSite=Strict`, cabeçalho da aplicação e validação de origem para mutações do navegador. Nenhum dos controles o torna apropriado para internet ou produção. `PetEngine`/SQLite e a alteração de política dentro do próprio processo continuam APIs confiáveis; código Python local arbitrário e processos com acesso à conta podem contorná-los. Falta autenticação por identidade de cliente, TLS, auditoria de segurança externa e proteção robusta contra abuso. Uma conexão F9 real continua pendente de projeto e validação.

Exemplo local para **consultar** o contexto após conceder `shareData` na interface: coloque apenas o *caminho* de `bridge.token` na variável de ambiente, não o token em si. O exemplo não representa uma integração F9.

```python
import json, os
from pathlib import Path
from urllib.request import Request, urlopen

token = Path(os.environ["PET_BRIDGE_TOKEN_FILE"]).read_text(encoding="ascii").strip()
request = Request("http://127.0.0.1:8765/api/bridge/context",
                  headers={"Authorization": f"Bearer {token}"})
with urlopen(request) as response:
    print(json.load(response)["context"])
```

## Entrada

`POST /api/bridge/events` aceita exatamente:

```json
{
  "eventId": "evt-example-001",
  "eventType": "AGENT_TASK_COMPLETED",
  "timestamp": "2026-10-28T15:00:00-03:00",
  "source": "muse-agent",
  "payload": { "taskId": "task-001", "success": true }
}
```

`eventId`, `source` e IDs no payload: 1–120 caracteres `A–Z a–z 0–9 _ . : @ -`, pseudônimos, sem dados pessoais. `auto:` é reservado ao scheduler. Timestamp deve ser ISO 8601 com fuso. O relógio de recebimento determina o dia para limites de XP. Um reenvio com o mesmo `eventId` deve ter exatamente os mesmos tipo, origem, timestamp e payload: retorna `duplicate: true`, sem reaplicar. Mesmo ID com conteúdo diferente retorna 409. Tarefas, metas, habilidades novas e marcos têm ainda uma deduplicação lógica por tipo + origem + ID.

| Evento | Payload permitido | Efeito |
|---|---|---|
| `CHAT_MESSAGE_SENT` | `meaningful?: boolean` | Interação; primeiro contato diário e, quando declarado significativo, XP limitado. Nunca envia texto. |
| `AGENT_TASK_STARTED` | `taskId?: string` | Sinal de foco, sem XP. |
| `AGENT_TASK_COMPLETED` | `taskId`, `success: true` | XP de tarefa confirmada e memória genérica. |
| `AGENT_TASK_FAILED` | `taskId?: string` | Sem punição ou XP. |
| `GOAL_CREATED` | `goalId?: string` | Aceito sem XP. |
| `GOAL_COMPLETED` | `goalId`, `success: true` | XP de meta confirmada. |
| `APPROVAL_REQUIRED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED` | `{}` | Aceitos, sem alterar confiança ou punir rejeição. |
| `MEMORY_UPDATED` | `{}` | Aceito sem copiar memória pessoal do agente. |
| `TOOL_EXECUTION_COMPLETED` | `skillId`, `success: true`, `isNew: boolean` | XP somente se `isNew` for verdadeiro; skill deduplicada. |
| `MILESTONE_ACHIEVED` | `milestoneId`, `confirmed: true` | XP de marco e evento de recompensa/milestone. |

Campos extras são rejeitados. `success: false`, ausência de confirmação ou `confirmed: false` não são aceitos como conclusão. Tipos não reconhecidos retornam 400. O retorno de sucesso da ponte contém somente `duplicate`, `duplicateKind` e `xpAwarded`; não inclui `state`.

## Saída

`GET /api/events?after=<seq>&limit=100` retorna eventos persistidos ordenados por `seq` com `eventId`, `eventType`, `timestamp`, `source` e `payload`. A página pode ser retomada após reiniciar; o consumidor deve persistir o último `seq` processado e ser idempotente. Tipos:

- `PET_MOOD_CHANGED`
- `PET_LEVEL_UP` (inclui `mediaKey: milestone_video`)
- `PET_EVOLUTION_UNLOCKED` (eixos `LEVEL` ou `SPECIALIZATION`)
- `PET_ACTIVITY_STARTED` / `PET_ACTIVITY_COMPLETED`
- `PET_BOND_CHANGED`
- `PET_REWARD_UNLOCKED`

`GET /api/bridge/context` devolve apenas `petId`, `mood`, `traits` dominantes, `bond`, `level` e `currentActivity`. Se um futuro LLM utilizar esse contexto, ele é uma sugestão de estilo e **não** pode prevalecer sobre precisão, segurança, consentimento ou cumprimento da tarefa. O protótipo não invoca LLM algum.

## Outras rotas do protótipo

- `GET /api/state` reconcilia o tempo e pode executar um ciclo autônomo vencido.
- `POST /api/actions`: `{ "action": "PLAY|REST|EXPLORE|LEARN|CREATE|CHAT", "eventId": "...", "meaningful": false }`.
- `POST /api/autonomy/run`: `{ "activity": "DREAM|EXPLORE|EXPERIMENT|JOURNAL", "eventId": "..." }`.
- `GET/POST /api/config`, `POST /api/customization`, `GET /api/memories?limit=100&offset=0`, `DELETE /api/memories[/<id>]`.
- `GET /api/awards?limit=20&offset=0`, `GET /api/autonomy/history?limit=20&offset=0` e `GET /api/media`; o retorno de listas possui `hasMore`.
- `POST /api/media/<slot>` recebe bytes brutos da mídia aprovada; `GET /media/<slot>` suporta `Range`; `DELETE /api/media/<slot>` remove a referência e os bytes sem outras referências.

Todas as rotas de dados e mídias listadas nesta seção exigem o proprietário; a ponte usa sua própria credencial e os escopos de consentimento descritos acima. O mecanismo atual não determina o transporte, autenticação, persistência, versões ou política da F9 real.
