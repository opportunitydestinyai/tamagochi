# Revisão final · área Tamagotchi web

**28/10/2026.** Inspeção local do código, das quatro seções de `GET /` e das evidências já existentes. A integração com Muse Android é futura; backup remoto é uma pendência separada e não bloqueia esta revisão web.

> Atualização de 29/10: a suíte de evolução foi executada novamente, e os rótulos internos de humor e tendência no Diário/Memórias foram corrigidos apenas na apresentação. Veja [ENTREGA_WEB.md](ENTREGA_WEB.md). Os resultados abaixo descrevem a revisão de 28/10.

## Fluxos e regras conferidos

| Seção | Estado observado nas evidências anteriores |
|---|---|
| **Meu slime** | Seis ações, atributos, humor e feedback; em banco novo, a sequência testada terminou com 23 XP e persistiu após recarga. O placeholder identifica a ausência da mídia aprovada. |
| **Minha jornada** | Nível derivado de XP, progresso relativo ao nível, seis estágios, recompensas de ambiente, tendências independentes e histórico de XP. |
| **Diário** | Quatro atividades manuais locais e histórico; a execução manual funciona com o agendamento desligado e persistiu após recarga. |
| **Memórias** | Consulta e exclusão de registros genéricos; o ledger de IDs e XP permanece para deduplicação. |

A fórmula padrão continua `arredondar(100 × (n−1)^1,5)`, com estágios nos níveis **1, 5, 10, 20, 35 e 50**. Limites diários, idempotência e operação transacional permanecem nas regras existentes. As cinco transições na interface foram testadas na revisão anterior **com dias simulados**, não com uso real prolongado: detalhes e valores em [AREA_EVOLUTIVA.md](AREA_EVOLUTIVA.md).

## Inconsistências reproduzidas e corrigidas

As reproduções usam Chromium e bancos descartáveis. O servidor havia respondido; o teste reteve apenas a entrega ao navegador para ordenar a corrida.

- **Memórias:** uma página antiga de “Mostrar mais” chegava após exclusão na mesma aba. Na exclusão individual, a UI chegou a mostrar 182 itens (181 únicos) e total 182 enquanto a API indicava 181. Após exclusão total, reapareceram **81 itens e total 181** na tela, embora a API informasse zero. Nenhum registro foi recriado no banco: a inconsistência era visual.
- **Diário:** uma nova atividade concluída durante a leitura de uma página antiga deixou a UI com **23 de 24 registros**, sem botão para carregar o item omitido. O registro continuava na API.
- **API de Memórias:** em uma exclusão concorrente controlada entre as duas transações anteriores da rota, a resposta continha **4 registros e total 0**. Era uma resposta internamente inconsistente.

`web/app.js` agora descarta páginas de Memórias e de histórico do Diário se uma mutação local foi concluída ou se uma atualização substituiu a lista durante a leitura. O botão volta a ficar disponível; se a resposta for descartada, pode ser necessário selecionar **Mostrar mais** novamente. `pet/service.py` e `app.py` leem a página de Memórias e sua contagem na mesma transação, sem alterar o contrato JSON.

**Depois:** exclusão individual manteve 100 itens únicos da primeira página e total/API 181; exclusão total manteve UI/API em zero. A nova atividade deixou a primeira página do Diário com 20 itens e o botão disponível; nova leitura recuperou os **24 itens únicos**. Outro teste alterou o banco numa segunda página e atualizou explicitamente a primeira: a página antiga foi descartada e o item deslocado pôde ser carregado. A API retornou página e total coerentes na exclusão concorrente.

Essas proteções não criam sincronização instantânea nem um snapshot global entre abas/endpoints. Uma resposta coerente capturada antes de uma alteração em outra aba pode estar desatualizada até a próxima atualização. A política anterior de recarga/posição de Memórias e Diário não foi alterada.

## Testes

- **Nesta revisão:** 83 testes Python passaram; `test:pagination` e `test:browser` passaram após as correções. A regressão HTTP e os três cenários direcionados de navegador também passaram. A falha esperada antes da correção e as saídas atuais estão em [revisao-final.log](revisao-final.log).
- **Execução anterior, sem repetição desnecessária:** `test:evolution` passou na revisão da área evolutiva, antes desta correção de paginação; cobriu ações, recarga, retorno de visibilidade e cinco transições com dias simulados. Não foi reexecutado nesta revisão. O código de XP, estágios e mídias não foi alterado.
- `test:browser` usa vídeo de cores sem personagem e uma flag que libera autoplay; não valida os recursos aprovados nem o autoplay normal.

Não houve teste físico Android nem validação das mídias SL-001 aprovadas ou do player F8/F9 real. `Muse-REA` não foi localizado na verificação anterior e **não houve backup remoto**. O ZIP é apenas uma cópia local, sem banco de execução e sem prova de entrega independente.
