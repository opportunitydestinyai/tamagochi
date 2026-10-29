# Inspeção de fluxos locais e sincronização · 28/10/2026

> Atualização posterior: a falha de paginação descrita nesta inspeção histórica foi corrigida. A recarga recupera os itens do histórico de XP na mesma aba quando o armazenamento está disponível. Veja [`PAGINACAO.md`](PAGINACAO.md) e, para a inspeção e correção posterior de foco, [`JORNADA_E_ACESSIBILIDADE.md`](JORNADA_E_ACESSIBILIDADE.md); as observações antigas abaixo foram preservadas como registro do antes.

## Escopo e método

Foi inspecionado o protótipo web/Python/SQLite deste checkout, não o aplicativo Muse Android. Os fluxos foram executados em Chromium 153, Python 3.11 e bancos SQLite descartáveis; não foram necessários F8/F9, Drive, Android físico ou arquivos SL-001. Não há personagem substituto: o habitat mostra um aviso de mídia ausente. Os estados avançados são produzidos por ações do motor com relógio simulado, não por dias reais de uso.

Os resultados são **observações locais**, não verificação independente, teste com leitor de tela, prova de integração ou backup remoto. A saída completa com comandos está em [`fluxos-locais.log`](fluxos-locais.log). As capturas são do navegador automatizado em `evidencias-fluxos/`.

## Telas e navegação

| Caminho | Conteúdo observado | Captura |
|---|---|---|
| **Meu slime** | Habitat com placeholder explícito, humor, nível/estágio, XP, felicidade, energia, vínculo e seis ações; “Ver todos” mostra os seis atributos. | [`01-visao-inicial.png`](evidencias-fluxos/01-visao-inicial.png), [`05-atributos-apos-acoes.png`](evidencias-fluxos/05-atributos-apos-acoes.png) |
| **Minha jornada** | Linha dos seis estágios, nível atual, tendência/especialização e histórico de concessões de XP. | [`04-jornada-descoberta.png`](evidencias-fluxos/04-jornada-descoberta.png), [`09-evolucao-durante-uso.png`](evidencias-fluxos/09-evolucao-durante-uso.png) |
| **Diário** | Registros locais do pet, quatro atividades locais e histórico de autonomia. | [`06-diario-local.png`](evidencias-fluxos/06-diario-local.png) |
| **Memórias** | Registros do pet, contagem e comandos de exclusão; o texto digitado no chat não é armazenado. | [`07-memorias-locais.png`](evidencias-fluxos/07-memorias-locais.png) |

O teste navega **Minha jornada → Diário → Memórias → Meu slime**, verifica o item ativo, listas e atributos e recarrega a página. O teste geral cobre também configurações, consentimento/revogação, exclusões, privacidade e layouts desktop/celular. Na inspeção, a frase da tela de memórias que mencionava “preview” no sandbox era texto legado. Ela foi corrigida posteriormente; o servidor continua aceitando apenas loopback e não oferece preview remoto. Veja a [revisão da área evolutiva](AREA_EVOLUTIVA.md).

## Seis ações e persistência

Valores após cada ação **na mesma sequência**, partindo de um banco novo com regras padrão. F/E/C/K/V/T = felicidade, energia, curiosidade, conhecimento, vínculo e confiança; a UI arredonda os atributos. O bônus diário e limites de XP dependem do histórico, portanto estes números não são promessa para qualquer sequência.

| Estado/ação | F | E | C | K | V | T | XP total | Humor exibido |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Inicial | 75 | 80 | 50 | 10 | 20 | 50 | 0 | Tranquilo |
| Brincar | 83 | 70 | 50 | 10 | 23 | 51 | 5 | Empolgado |
| Descansar | 83 | 90 | 50 | 10 | 23 | 51 | 5 | Descansando |
| Explorar | 85 | 82 | 55 | 10 | 23 | 51 | 5 | Curioso |
| Aprender | 85 | 75 | 57 | 14 | 23 | 51 | 13 | Concentrado |
| Criar | 88 | 68 | 59 | 14 | 23 | 51 | 21 | Concentrado |
| Conversar, texto acima do limite configurado | 90 | 68 | 59 | 14 | 25 | 52 | 23 | Concentrado |
| Após recarregar | 90 | 68 | 59 | 14 | 25 | 52 | 23 | Concentrado |

No cenário, os primeiros 5 XP vêm da primeira interação diária; Aprender e Criar concedem 8 XP cada e a conversa significativa, 2 XP. A conversa responde com texto pré-definido no navegador: envia somente um booleano derivado do comprimento, não o conteúdo digitado. A tela recarregada é verificada contra `/api/state`, e o teste Python `tests/test_engine.py::test_02_persist_and_restart` verifica adicionalmente persistência após recriar o motor.

## Evolução verificada

- A fórmula padrão de XP acumulado para o nível `n` é `arredondar(100 × (n − 1)^1,5)`; os primeiros limiares são **0, 100, 283, 520, 800 e 1118 XP**. Os estágios começam nos níveis **1, 5, 10, 20, 35 e 50**.
- No navegador, uma conversa local leva **98 → 105 XP**, alterando nível 1 → 2. A barra mostra **5/183 XP** dentro do nível e permanece assim após recarga.
- Em **150 XP**, a barra do nível 2 mostra **50/183 = 27,3%**, não 150/183. Em outra configuração, a 1 XP do limiar mostra 99,9%, não 100%. Captura: [`03-nivel2-150xp.png`](evidencias-fluxos/03-nivel2-150xp.png).
- O cenário `stage5-edge` usa ações com dias simulados até **797 XP / nível 4 / Despertar**. No navegador, **Criar** recebe 5 XP da primeira interação do novo dia mais 8 XP da ação: **797 → 810**, nível 5 e estágio **Descoberta**. A notificação é exibida e a recarga preserva estágio e **10/318** dentro do nível. A captura [`09-evolucao-durante-uso.png`](evidencias-fluxos/09-evolucao-durante-uso.png) mostra a transição e a especialização Pesquisador.
- O motor registra `PET_EVOLUTION_UNLOCKED` com a recompensa “Moldura de descoberta” e `mediaKey=milestone_video`. Isto comprova o evento local, **não** a existência ou reprodução do vídeo aprovado.

## Lacuna corrigida: leitura antiga sobrescrevia uma ação

**Reprodução antes da correção**, na cópia extraída do ZIP local anterior: o Chromium pausou, na resposta, uma leitura legítima de `/api/state`; foi acionado **Brincar** e a resposta antiga foi liberada depois. A UI mostrou primeiro XP 5/felicidade 83/energia 70/vínculo 23, mas voltou para XP 0/75/80/20, apesar de a API conservar XP 5/83/70/23. A recarga restaurou os valores corretos. Portanto, era uma regressão visual, não perda de transação no SQLite.

**Correção:** em [`web/app.js`](../web/app.js), `serializeMutation` e `applyMutationState` (linhas 185–195) ordenam, na mesma aba, as mutações que retornam estado. `refreshSnapshot` (196–214) confere uma revisão local antes e depois das leituras e repete a captura se uma alteração local for concluída durante elas. `refresh` (215–230) agrupa pedidos pendentes, preserva `includeMedia` e recupera a fila após erro. Exclusões de memória e mudanças de mídia também invalidam leituras em andamento. O chat usa uma geração do diálogo para não restaurar texto depois de fechado.

**Depois:** o mesmo tipo de atraso conserva na tela e na API **XP 5, felicidade 83, energia 70 e vínculo 23**, inclusive após recarga; ver [`08-apos-resposta-atrasada.png`](evidencias-fluxos/08-apos-resposta-atrasada.png). O teste em [`tools/e2e-evolution.cjs`](../tools/e2e-evolution.cjs) também retém uma lista antiga, sobrepõe Brincar/Descansar e Brincar/Sonhar, verifica agrupamento de oito atualizações, testa chat fechado com resposta atrasada e injeta falhas de leitura e escrita. Cada ação esperada é observada uma vez; a fila continua utilizável após as falhas simuladas.

A proteção é **por aba**, não um mecanismo global de versão. Alterações por outra aba, scheduler ou futura integração não invalidam essa revisão local, e endpoints separados não garantem um snapshot transacional único. Uma requisição que nunca termina não tem timeout específico.

## Testes executados nesta revisão

| Verificação | Resultado local |
|---|---|
| `python3 -m unittest discover -s tests -v` | **77 passaram**; inclui persistência/reinício, fórmula, deduplicação, autonomia, HTTP e paginação da API. |
| `npm run test:browser` | **Passou** em desktop/celular, inclusive consentimento e privacidade; usa vídeo neutro e força autoplay. |
| `npm run test:evolution` | **Passou duas vezes**, com bancos descartáveis; a primeira execução gerou nove capturas. |
| `tests/evolution_scenario.py` | Passou com ações e relógio simulado, da criação ao estágio 5. |
| `compileall` e `node --check` | Passaram para os arquivos Python/JS verificados. |
| `node tools/inspect-pagination.cjs` | **Na revisão anterior, saiu com código 1**. O diagnóstico ampliado passou depois da correção; veja `PAGINACAO.md`. |

Os testes do navegador usam `puppeteer-core` e um executável Chromium; os comandos exatos e o ambiente usado estão no log. `ARIA` da barra foi verificada automaticamente, sem leitor de tela. Não foi realizada nova medição de cobertura nesta revisão.

## Outras lacunas e pendências

1. **Paginação do histórico de XP — observação histórica, corrigida posteriormente:** em uma base com 122 concessões, o primeiro “Mostrar mais” exibiu 20 → 40 itens, mas ocorreu `Cannot set properties of null (setting 'disabled')` e o botão permaneceu desabilitado. Depois de Descansar, a atualização voltou a exibir 20 itens, ainda com o botão desabilitado. A API retornou 123 concessões e confirmou que todas as 122 anteriores permaneceram. O padrão era o uso de `event.currentTarget` após `await`; a reprodução dinâmica descrita é do histórico de XP. A correção e o diagnóstico atual, agora aprovado, estão em `PAGINACAO.md`.
2. As mídias definitivas SL-001, o player/especificação F8, a integração F9 e autoplay sob política normal continuam sem validação; o vídeo usado no teste geral é neutro. Não se alteraram arquivos F1–F9 neste checkout, onde eles não estavam presentes.
3. O Drive estava conectado, mas `Muse-REA` não foi localizado: **nenhum upload, backup remoto ou link foi verificado**. O ZIP e o hash locais não provam acesso independente ou backup.
4. Não há APK, teste Android físico nem integração Muse Android pronta; essa integração é uma etapa **futura**, não requisito desta inspeção. Leitor de tela e auditoria externa de segurança também seguem pendentes.
