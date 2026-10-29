# Arquitetura e operação

```text
Navegador responsivo (HTML/CSS/JS; player adaptador)
              | JSON/HTTP de mesma origem
        app.py · HTTP local
              |
        PetEngine (transações)
          /      |       \
   Regras    Scheduler   MusePetBridge
          \      |       /
          SQLite + outbox + memórias
```

O domínio não importa classes F1–F9. `pet/model.py` contém `MoodEngine`, `PersonalityEngine`, `ExperienceEngine`, `EvolutionEngine` e `ActivityEngine`; `pet/service.py` coordena `PetEngine`; `pet/autonomy.py` expõe `AutonomyScheduler`; `pet/repository.py` administra SQLite e migrações; `pet/bridge.py` valida o contrato; `pet/media.py` preserva as mídias importadas. A UI não calcula XP ou especialização. O repositório inicial desta sessão continha apenas `README.md`, portanto o Muse F9 e o player F8 não estavam disponíveis para inspeção.

## SQLite e recuperação

- Migração transacional versionada por `PRAGMA user_version` (atualmente **2**); bancos mais novos que o código são rejeitados. Uma migração v1→v2 acrescenta `meaningfulChatMinChars` preservando estado e configurações.
- `pet`: estado e configuração persistidos em JSON. `processed_events`: ID e fingerprint de entrada; `logical_events`: identidade de tarefa/meta/habilidade/marco; `xp_awards`: razão, valor, dia e idempotência; `pet_events`: outbox ordenada; `memories` e `autonomy_history`: registros consultáveis.
- Cada comando usa `BEGIN IMMEDIATE` e grava estado, deduplicação, XP, memórias e eventos de saída na **mesma transação**. Falhas revertem tudo. Chamada repetida com mesmo ID/conteúdo não reaplica efeitos; mesmo ID com outro conteúdo retorna 409. Tarefas/metas/marcos e novas skills também são deduplicados por origem + ID lógico, mesmo com outro ID de evento. O prefixo `auto:` é reservado ao agendador.
- O outbox é consultável por sequência; uma integração futura deve guardar seu cursor depois de processar cada evento e lidar com repetição. SQLite serializa escritores; há testes com eventos concorrentes.
- `lastUpdatedAt` é um marco de tempo de alta-water: relógio para trás não é usado para recuperar energia repetidamente. Tempo avançado é limitado a 24 h por reconciliação por padrão; apenas há recuperação leve de energia, sem perda de felicidade/vínculo ou morte. O relógio pode ficar congelado até alcançar o marco depois de uma reversão.

## Sincronização da interface local

A interface serializa na mesma aba as mutações que retornam estado (ações, atividades locais, conversa, personalização e configuração). Cada resultado aplicado incrementa uma revisão local; exclusão de memórias e importação/remoção de mídia também a invalidam. Uma leitura que atravessa uma dessas alterações é refeita antes de atualizar a tela. Atualizações aguardando outra leitura são agrupadas, preservando a solicitação de incluir mídia; falhas não bloqueiam as próximas operações. Isso evita que uma resposta anterior apague visualmente o resultado de uma ação já concluída. A conversa também descarta a resposta visual atrasada se a janela tiver sido fechada.

O mecanismo é por aba e não é controle de versão global: uma alteração feita simultaneamente por outra aba, pelo agendador ou por uma integração futura não é detectada pela revisão local; a atualização periódica posterior pode refletir o estado novo. As listas são obtidas por rotas separadas e não constituem um snapshot transacional entre todos os endpoints. Respostas que nunca terminam não têm timeout próprio.

Para evitar reapresentar eventos antigos na abertura de históricos longos, a UI consulta primeiro `GET /api/ui/events/cursor` (exclusivo do proprietário), que retorna `MAX(seq)` dos eventos confirmados. Depois obtém o estado e busca notificações posteriores à fronteira; um evento gravado entre o cursor e o estado continua visível. As buscas posteriores permanecem limitadas a 20 páginas de 500 eventos por ciclo. Regressão e limites em `reports/AREA_EVOLUTIVA.md`.

Na jornada, `GET /api/awards` devolve página e contagem total lidas na mesma transação SQLite. Os controles assíncronos guardam o botão antes do `await` e encerram o estado ocupado no `finally`. A paginação de XP, as cinco ações diretas e o envio da conversa usam `aria-disabled` com guarda de reentrada para não perder foco; a jornada tem anúncio de status e, se o foco não tiver mudado, leva ao primeiro item novo. Atualizações preservam o registro focado por evento e motivo. Outros controles não foram auditados de forma equivalente. A interface ordena a paginação de XP com as atualizações e mantém a quantidade já carregada. Como o ledger é apenas acrescentado, novos registros no início aumentam a janela para conservar os itens anteriores; se o total mudar entre páginas, a leitura é refeita. Para recarga, somente as contagens de itens carregados e total ficam em `sessionStorage` da aba, sem IDs, texto ou credenciais. A restauração ocorre enquanto o armazenamento estiver disponível; se estiver bloqueado, atualizar ainda funciona na página aberta, mas a recarga volta à primeira página. Não foi definido retorno à tela anterior, posição de rolagem ou política durável entre sessões. A restauração de itens se aplica apenas à jornada; os botões de paginação de Memórias/Diário também foram corrigidos, sem mudar sua política de recarga. Detalhes e limites: `reports/PAGINACAO.md`.

A página e o total de `GET /api/memories` são lidos na mesma transação SQLite. Leituras paginadas de Memórias e de histórico do Diário descartam uma resposta se uma mutação local foi concluída ou se um refresh substituiu a lista enquanto a leitura aguardava; o botão pode ser acionado novamente. Não é sincronização instantânea entre abas nem snapshot global. Evidências: `reports/REVISAO_FINAL.md`.

## Autonomia

Desativada por padrão. Uma verificação de estado executa no máximo **um** trabalho atrasado; a página visível verifica a cada 60 s, sem polling frenético. Intervalo configurável de 15 a 1440 minutos, horários de descanso por fuso IANA, custo energético, rotação de quatro atividades, histórico, pausa e cancelamento de ciclos futuros. Se o início e fim de descanso forem iguais, não há janela de descanso. Uma falha tratada reverte o ciclo e tenta registrar `FAILED` e reagendar em 15 minutos; se o armazenamento estiver indisponível, o registro de falha também pode falhar. Uma interrupção abrupta antes do commit deixa o ciclo original pendente e seguro para repetir. Não há execução enquanto o processo estiver parado; Android WorkManager/limites do SO exigem implementação e testes futuros.

Sonhar contabiliza registros locais do pet sem inventar fatos do usuário. Explorar usa uma lista local, não pesquisa externa. Experimentar combina textos pré-definidos, não um LLM. Diário cria um resumo local do estado. A execução manual é explícita; a janela de descanso controla apenas o agendamento automático.

## Privacidade e segurança

Não existem chamadas de rede de terceiros, SDKs de analytics ou APIs pagas no código de execução. A ponte rejeita payloads fora de uma whitelist, inclusive texto livre; não insira segredos em IDs. O formulário de conversa processa o texto no navegador e não o envia: o servidor recebe apenas um indicador aproximado de comprimento. Ao fechar, entrada e conversa visíveis são limpas, mas uma operação pendente pode manter uma cópia temporária em memória; isso não é apagamento seguro. Memórias podem ser paginadas e apagadas; o log técnico de IDs/outbox e o ledger permanecem para idempotência, e um reset integral exige remover o banco com o servidor parado.

O servidor rejeita bind que não seja loopback IPv4 e não aceita proxy/preview remoto. Dois tokens aleatórios locais e distintos são gerados por execução: o do proprietário protege dados/mídias e a sessão do navegador; o da ponte protege entrada e saída, cada qual com consentimento independente, desligado por padrão e limitado a 8 horas. O proprietário pode revogar; reiniciar ou bloquear a sessão também revoga. O histórico local para a interface usa rota de proprietário separada. Não há CORS permissivo; Host/Origin são validados, cookies têm `HttpOnly`/`SameSite=Strict`, e há um cabeçalho de aplicação para a sessão. Tokens não são gravados no SQLite nem incluídos no snapshot/ZIP; os arquivos temporários privados não devem ser compartilhados.

Esses controles são para teste local, não produção: não há TLS, segregação por identidade de cliente, defesa robusta contra abuso ou auditoria externa. Um processo com acesso à conta pode ler arquivos de credenciais e código dentro do processo pode acessar o motor/SQLite diretamente. No Android, preservar a fronteira de domínio e contrato, portar ou reimplementar o core em Kotlin/Room, avaliar WorkManager e integrar o player aprovado. Isto é um caminho de integração, **não uma implementação Android existente**.
