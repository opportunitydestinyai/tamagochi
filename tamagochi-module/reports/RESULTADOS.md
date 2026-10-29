# Relatório de validação · 28/10/2026

> Registros locais, não verificação independente de links, ZIP ou backup. Os 55 testes e 90% de cobertura da revisão original são históricos e não medem as alterações posteriores.

## Entrega web · 29/10/2026

Após uma correção de apresentação dos rótulos de humor e tendência no Diário e em Memórias, passaram as três suítes de navegador, incluindo novamente as cinco transições com dias simulados. Os 83 testes Python passaram antes dessa mudança exclusivamente JavaScript; o código Python permaneceu inalterado. Telas, evidências e limites em [`ENTREGA_WEB.md`](ENTREGA_WEB.md) e `entrega-web.log`. Naquela revisão, não houve APK nem publicação no GitHub.

## Revisão final da área web

Na revisão final, foram reproduzidas e corrigidas páginas atrasadas de Memórias/Diário que podiam mostrar dados obsoletos após uma exclusão ou atividade, além de uma contagem inconsistente na API de Memórias. Passaram **83 testes Python**, `test:pagination` e `test:browser`. `test:evolution` não foi repetido: sua execução anterior cobriu as cinco transições com dias simulados e não houve mudança nas regras de XP ou estágio. Não há garantia de atualização instantânea entre abas. Evidências e limites: [`REVISAO_FINAL.md`](REVISAO_FINAL.md).

## Revisão da área evolutiva

Em 28/10/2026, passaram localmente **82 testes Python** e as três suítes de navegador. Com bancos descartáveis, foram verificados as seis ações, quatro telas, quatro atividades manuais, recarga, retorno `hidden → visible` por minimização/restauração headless e as cinco transições entre estágios, com dias simulados. Foi reproduzido e corrigido o reaparecimento de aviso antigo em histórico com mais de 10.000 eventos; XP e estágio já estavam corretos. A correção inicializa o cursor na fronteira do histórico e não altera as regras de XP ou a mídia. Os resultados não validam troca manual de aba, reprodução do personagem ou integração Android. Sem nova medição de cobertura. Detalhes: [`AREA_EVOLUTIVA.md`](AREA_EVOLUTIVA.md) e `area-evolutiva.log`.

## Revisão de conversa e convivência

Em 28/10/2026, passaram localmente **80 testes Python** e as três suítes de navegador. Com dados descartáveis, a revisão acompanhou chat curto/elegível, registros genéricos, atributos e XP em quatro telas, bloqueio e novo login, outro contexto e reinício limpo de processo com o mesmo SQLite. Uma fixture com dias simulados cruzou de 797 para 804 XP por conversa, chegando a Descoberta e permanecendo após reiniciar. Um teste de relógio simulado verificou a expiração do humor; o teste entre sessões atualizou a primeira aba explicitamente. Nenhuma divergência de interface foi reproduzida que justificasse correção de produto, e não houve nova medição de cobertura. Detalhes, trechos e limites: [`CONVIVENCIA_CONTINUA.md`](CONVIVENCIA_CONTINUA.md) e `convivencia-continua.log`.

## Revisão da jornada e teclado

Em 28/10/2026, passaram localmente **78 testes Python** e os testes de navegador geral, evolução e paginação. Com bancos descartáveis, foram observados os estados vazio, com registro, expandido e após recarga, além das seis ações. Corrigiram-se perdas reais de foco no atalho da jornada, na paginação de XP, nas ações principais e no envio da conversa; foram exercitados Tab/Enter, falha, reentrada, mudança de foco durante espera e a árvore de acessibilidade do Chromium. Isso não substitui teste com leitor de tela nem valida acessibilidade integral. A instrumentação CDP anterior falhou intermitentemente em execuções paralelas e foi substituída no teste; detalhes e execuções em [`JORNADA_E_ACESSIBILIDADE.md`](JORNADA_E_ACESSIBILIDADE.md) e `jornada-acessibilidade.log`.

## Revisão de paginação

Em 28/10/2026, a correção do botão e da restauração de itens da jornada passou em **78 testes Python**, no teste geral de navegador, no teste de evolução/sincronização e em duas execuções do teste de paginação. A regressão cobre mais de 20 itens, novas concessões, recarga da mesma aba, falhas de rede, concorrência e mais de 500 itens. A mesma causa foi corrigida nos botões de Memórias/Diário. A recarga continua abrindo a tela inicial; rolagem e política entre sessões não foram especificadas nem alteradas. Detalhes, limitações e log: [`PAGINACAO.md`](PAGINACAO.md) e `paginacao.log`.

## Revisão de fluxos locais e sincronização

Em 28/10/2026, passaram **77 testes Python**, o teste geral de navegador e duas execuções do teste de evolução e concorrência. Uma resposta antiga de estado que apagava visualmente o resultado de uma ação foi reproduzida antes e corrigida na mesma aba; os testes cobrem leitura/lista atrasada, ações sobrepostas, falhas e chat. As seis ações, quatro telas, mudança de nível/estágio e recarga foram observadas com bancos descartáveis; os estados avançados usam dias simulados. Naquela revisão, o diagnóstico de paginação saiu com **código 1**: o primeiro “Mostrar mais” deixava o botão desabilitado e uma atualização voltava à primeira página; os registros permaneciam na API. A lacuna foi corrigida na revisão posterior descrita acima. Detalhes históricos: [`FLUXOS_LOCAIS.md`](FLUXOS_LOCAIS.md) e `fluxos-locais.log`.

## Revisão de experiência e progresso

Em 28/10/2026, passaram **77 testes Python**, o teste geral de navegador e o novo teste de evolução. A revisão corrigiu a inconsistência entre a fração de XP acumulado e a barra relativa ao nível, além do arredondamento prematuro a 100%; são verificados nível 1, transição local 1→2, 100/150 XP, estágio 5, atributos ARIA, fórmula configurada e recarga. O cenário de níveis avançados usa ações locais e dias simulados em bancos temporários. Detalhes, trechos, limitações e capturas: [`EXPERIENCIA_EVOLUTIVA.md`](EXPERIENCIA_EVOLUTIVA.md); log: `experiencia-evolutiva.log`. A revisão não mediu novamente cobertura; a medição abaixo continua sendo da revisão de segurança.

## Revisão de autenticação e consentimento

Em 28/10/2026 às 18:46 (-03), a saída local registrada em `seguranca-ponte.log` indica **19 testes específicos de segurança** e **74 testes Python no total** aprovados. O teste de navegador também terminou com `OK` para sessão, consentimento e revogação, além das verificações anteriores, usando fixture de vídeo neutra e autoplay liberado por flag. A medição com ramificações informou 88,83% de linhas e 81,48% de ramificações nos módulos Python selecionados; não mede JavaScript nem subprocessos CLI. Não é auditoria independente nem prova de segurança em produção.

## Resultado resumido da revisão anterior

- **55 testes automatizados Python passaram, sem casos ignorados**, executados em bancos temporários: estado inicial e persistência, migração v1→v2, cálculo de humor, efeitos/energia, fórmula/níveis, limites de XP, evolução e recompensas, concorrência e deduplicação, contratos, autonomia e diário, personalização, ausência prolongada e reversão de relógio, exclusão de memória, falha de armazenamento e interrupção, mídia/bytes/hash, HTTP e paginação, exportação privada consistente e integridade do pacote. Log: `testes-unitarios.log`.
- **Teste de navegador Chromium passou** em viewport desktop 1440×1000 e celular 390×844: navegação, seis atributos, todas as ações principais, privacidade da conversa, personalização e persistência, atividades autônomas, ativação e cancelamento, exclusão de memórias, player com vídeo neutro, milestone e ausência de requisições externas. Log: `testes-navegador.log`.
- **Cobertura de linhas Python: 90%** para `pet`, `app` e `tools`, medida apenas durante os testes Python (`coverage` 7.10.7); não inclui JavaScript nem cobertura de ramificações e não garante ausência de defeitos. A fachada `AutonomyScheduler` passou de sem teste direto para 100% de linhas cobertas. Log: `cobertura-python.log`.
- Na revisão foi corrigido um problema em que notificações empilhadas podiam bloquear cliques no celular. Agora são não interativas e limitadas a três; há verificação de regressão no teste do navegador.
- O ZIP foi extraído em diretório temporário: hashes dos arquivos, 55 testes Python e o teste de navegador passaram também a partir da cópia extraída.
- O teste de codec usa um fixture sem personagem. **Não valida reprodução do SL-001 definitivo**, posters aprovados ou equivalência de transições com F8. Esses arquivos não foram disponibilizados.
- A ponte foi validada com os 12 tipos de entrada propostos; as saídas são verificadas por tipo, cursor, evento de nível/evolução/atividade/vínculo/humor e recompensa. Não houve integração com F9 real.
- A base Git desta sessão contém somente `README.md`; nenhum arquivo F1–F9 estava presente. Portanto não houve alteração de arquivos F1–F9 neste checkout, mas não se pode afirmar inspeção do aplicativo externo.
- Nenhuma chamada externa ou API paga na execução do protótipo foi observada no teste de navegador daquela revisão. O preview anterior foi encerrado; a versão atual recusa bind de rede/preview remoto.
- **Android físico: não testado.** Não foi gerado APK nem demonstrada integração nativa.
- **Google Drive: conectado, mas a pasta `Muse-REA` não foi localizada na conta acessível.** Upload, verificação e links diretos não foram realizados; critério de backup permanece aberto. É necessário receber o link da pasta ou acesso à conta correta. O ZIP local não equivale a backup no Drive.

## Mapeamento dos testes obrigatórios

| Item | Resultado |
|---|---|
| 1–4 criação, carregamento, persistência, humor | Passaram em testes automatizados. |
| 5–9 energia, XP, níveis, especialização e deduplicação | Passaram, incluindo chamadas concorrentes e eventos lógicos repetidos. |
| 10–14 autonomia, diário, reinício, ausência e limites | Passaram, incluindo descanso, cancelamento, falhas e interrupção. |
| 15 personalização | Passou, inclusive bloqueio/desbloqueio de recompensas. |
| 16 reprodução do slime | **Pendente**: apenas mecanismo HTML5 com vídeo de teste neutro foi validado. |
| 17 milestone | Evento e playback técnico com fixture passaram; mídia SL-001/F8 real **pendente**. |
| 18 contrato | Fixtures propostas passaram; integração F9 real **pendente**. |
| 19 sem chamadas pagas | Passou no código de execução e na observação das requisições do navegador. |
| 20 sem alterações F9 | Nenhum arquivo F9 existe neste checkout; nenhuma alteração F9 foi feita aqui. |

A suíte não é substituto de revisão de segurança, testes com acessibilidade assistiva, verificação em dispositivos Android, teste dos recursos aprovados ou revisão jurídica da licença.
