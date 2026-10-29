# Área Tamagotchi evolutiva · fluxo web local

> A revisão final posterior encontrou e corrigiu corridas de paginação de Memórias/Diário. A execução e os números abaixo são históricos; resultados atuais e limites estão em [REVISAO_FINAL.md](REVISAO_FINAL.md).

**28/10/2026.** Inspeção do protótipo Python/SQLite e de sua interface web, com Chromium e bancos descartáveis. A área é independente do Muse Android: a integração futura não foi necessária para executar estes fluxos. Não havia mídias aprovadas do SL-001, player F8 ou código F9 neste checkout. Não foi gerado outro personagem.

## O que está disponível e onde está

As quatro telas são seções da mesma página `GET /`, não rotas web independentes. `web/index.html` declara os controles; `web/app.js` alterna a seção ativa e a marca com `aria-current`.

| Tela/controle | Fluxo disponível | Implementação/rota local |
|---|---|---|
| **Meu slime** | Habitat, placeholder de mídia ausente, humor, nível, estágio, XP, três atributos em destaque, seis ações e acesso aos seis atributos. | `web/index.html` (`#view-home`); `renderState()` em `web/app.js`; `GET /api/state`. |
| **Minha jornada** | Seis estágios, estágio e nível atuais, recompensas de ambiente, tendências e histórico paginado de XP. O atalho “Ver jornada” e a navegação lateral levam à mesma seção. | `#view-evolution`, `setView()`/`renderState()`; `GET /api/awards`; regras em `pet/model.py`. |
| **Diário** | Registros do pet, quatro atividades manuais locais e histórico das execuções. O agendamento automático vem desligado, sem impedir as atividades manuais. | `#view-diary`; `POST /api/autonomy/run`, `GET /api/autonomy/history`, `GET /api/memories`. |
| **Memórias** | Consultar e apagar registros locais do pet; o ledger técnico de XP/IDs permanece para deduplicação. | `#view-memory`; `GET /api/memories` e `DELETE /api/memories[/id]`. |
| **Conversar / Ver todos / Personalizar / Configurações** | Diálogos para mensagem local, seis atributos, camadas do habitat e regras/consentimento/mídias aprovadas. | `web/index.html` (`dialog-*`), `web/app.js`; `POST /api/actions`, `/api/customization`, `/api/config` e rotas de mídia. |

Todas as rotas de dados da interface exigem sessão/credencial de proprietário; a ponte tem credencial e consentimento separados. As ações aplicam regras no `PetEngine` (`pet/service.py`) e são salvas transacionalmente no SQLite (`pet/repository.py`). `web/app.js` mostra o estado retornado e reconsulta as listas.

## Fluxo percorrido em banco novo

No navegador autenticado, o teste abriu **Meu slime → Minha jornada → Meu slime**, usou as seis ações, percorreu **Minha jornada → Diário → Memórias → Meu slime** e recarregou. As colunas são felicidade / energia / curiosidade / conhecimento / vínculo / confiança, arredondadas como na UI. Os valores seguem essa sequência específica, com limites e bônus diários padrão.

| Ação | XP acumulado | Humor | Atributos observados | Feedback textual observado |
|---|---:|---|---|---|
| Início | 0 | Tranquilo | 75 / 80 / 50 / 10 / 20 / 50 | Placeholder: “O SL-001 vai aparecer aqui / Adicione a mídia original aprovada”. |
| Brincar | 5 | Empolgado | 83 / 70 / 50 / 10 / 23 / 51 | “Um momento de brincadeira deixou o habitat mais alegre. +5 XP.” |
| Descansar | 5 | Descansando | 83 / 90 / 50 / 10 / 23 / 51 | “SL-001 descansou e recuperou energia.” |
| Explorar | 5 | Curioso | 85 / 82 / 55 / 10 / 23 / 51 | “Descoberta local: Jardins de luz...” |
| Aprender | 13 | Concentrado | 85 / 75 / 57 / 14 / 23 / 51 | “Aprendizado local — Luz do Sol...” e +8 XP. |
| Criar | 21 | Concentrado | 88 / 68 / 59 / 14 / 23 / 51 | “Ideia local: um jardim lilás...” e +8 XP. |
| Conversar, acima do limiar | 23 | Concentrado | 90 / 68 / 59 / 14 / 25 / 52 | “Momento registrado. +2 XP.” e resposta local pré-definida. |
| Após recarga | 23 | Concentrado | 90 / 68 / 59 / 14 / 25 / 52 | A UI retornou a **Meu slime** e os valores conferiram com `/api/state`. |

A jornada passou de histórico vazio para registros “Primeira interação do dia”, aprendizado, criação e conversa. Diário e Memórias exibiram lembranças genéricas. A barra de XP e os seis atributos foram comparados com a resposta da API, e a navegação verificada com apenas uma seção visível. O diálogo de conversa explicou que não é IA; para esta sequência respondeu: “Estou concentrado e tenho 68 de energia. Obrigado por este momento! Esta é uma resposta local pré-definida.” O texto digitado não é enviado pelo formulário; ver [análise de privacidade e continuidade](CONVIVENCIA_CONTINUA.md).

Capturas locais: [habitat inicial](evidencias-fluxos/01-visao-inicial.png), [diálogo de conversa](evidencias-area/10-conversa-local.png), [Diário](evidencias-fluxos/06-diario-local.png) e [Memórias](evidencias-fluxos/07-memorias-locais.png). As imagens de uma revisão anterior mostram o texto antigo de Memórias; a frase sobre um suposto preview foi corrigida nesta revisão.

Outra sequência isolada abriu **Diário** com agendamento desligado e executou manualmente Sonhar, Explorar, Experimentar e Escrever no diário. As energias observadas foram **78 → 73 → 68 → 66**; Experimentar levou o XP de 0 para 8. Após recarga, os quatro registros continuaram no histórico e o agendamento permaneceu desativado. As atividades são geradores locais, não um agente nem pesquisa na internet.

## Evolução percorrida

Foram preparados **bancos independentes com ações locais e relógio simulado**, respeitando as regras padrão e o ledger; os números não representam uso real prolongado. Em cada banco o navegador partiu antes de um limiar, acionou **Criar**, observou nível, estágio e notificação e recarregou:

| Transição na UI | XP antes → depois | Evidência de recompensa |
|---|---:|---|
| Despertar → **Descoberta**, nível 5 | 797 → 810 | Moldura de descoberta e notificação; recarga preservou o estágio. Uma conversa elegível em outra fixture fez 797 → 804. |
| Descoberta → **Aprendizado**, nível 10 | 2692 → 2705 | Emblema/indicação de estágio e linha atual na jornada; recarga preservou. |
| Aprendizado → **Companheiro**, nível 20 | 8275 → 8288 | Decoração Halo passou de bloqueada a disponível; recarga preservou o estágio. |
| Companheiro → **Explorador**, nível 35 | 19816 → 19829 | Tema Aurora passou de bloqueado a disponível; recarga preservou o estágio. |
| Explorador → **Evoluído**, nível 50 | 34293 → 34306 | Os seis estágios apareceram desbloqueados; Constelação passou de bloqueada a disponível, foi aplicada no habitat e persistiu após recarga. |

No último cenário, o motor preparou **377 dias simulados, 5.987 ações e 13.396 eventos**, não 377 dias de uso físico. As ações da interface receberam 5 XP da primeira interação do novo dia e 8 XP de Criar. Essas recompensas são camadas e indicações de interface; elas não substituem, redesenham ou alteram o personagem. Capturas: [Descoberta](evidencias-fluxos/09-evolucao-durante-uso.png) e [Evoluído com notificações](evidencias-area/11-estagio-evoluido.png).

A fórmula padrão e as faixas estão em `pet/model.py:52–87,194–226`; `pet/service.py` registra nível/evolução, recompensa e memória, e `web/app.js` exibe barra, moldura, estágio e mensagens. A mudança de nível e um evento com `mediaKey` não comprovam a reprodução de um vídeo real.

## Ao voltar à página

Foi usado Chromium headless, com minimização/restauração da janela pelo protocolo do navegador para produzir eventos reais `visibilitychange`, não uma troca manual em dispositivo físico:

1. A primeira página ficou em **Minha jornada**, XP 0, e passou a `document.hidden = true`.
2. Uma segunda página da mesma sessão usou **Brincar**: o banco passou a XP 5. A página oculta ainda mostrava XP 0, demonstrando ausência de sincronização instantânea.
3. Ao restaurar a primeira janela, ocorreu `hidden → visible`. Sem chamar `refresh()` manualmente, a UI buscou `/api/state`, mostrou **XP 5** e a concessão da primeira interação; **Minha jornada permaneceu aberta**. [Captura](evidencias-area/12-retorno-visibilidade.png).

O código também agenda atualização a cada 60 segundos enquanto visível, mas este teste não esperou nem cronometrou esse intervalo. Entre abas não existe versão global ou snapshot atômico entre todos os endpoints. Recarregar a página é diferente de retornar à visibilidade: a recarga abre Meu slime e não restaura a rolagem ou a tela anterior.

## Lacuna reproduzida e correção

Em um banco descartável com **13.396 eventos antigos**, a primeira abertura só avançava o cursor até 10.000 e marcava a inicialização como concluída. Na ação que mudou de nível 49 para 50, o estado e a jornada ficaram corretos, mas o aviso histórico “Novo nível: 49!” reapareceu junto das notificações reais do nível 50. A regressão adicionada falhou antes da correção:

```text
Avisos antes: Novo nível: 49! | Novo nível: 50! | Nova evolução: Evoluído.
Falha: níveis antigos não devem ser celebrados de novo.
```

A interface agora obtém **uma fronteira do histórico antes do primeiro snapshot**. A rota local de proprietário `GET /api/ui/events/cursor` consulta `MAX(seq)` no SQLite; os eventos posteriores são lidos pela rota existente. Nenhuma regra de XP, atributo, estágio ou mídia foi alterada:

```js
// web/app.js · antes do primeiro GET /api/state
if (!eventsInitialized) {
  const {cursor} = await api('/api/ui/events/cursor');
  eventCursor = cursor;
  eventsInitialized = true;
}
```

Depois, o mesmo cenário mostrou apenas o feedback de Criar, **“Novo nível: 50!”** e **“Nova evolução: Evoluído”**; a recarga não repetiu avisos antigos. Outro teste reteve a resposta do cursor, gravou uma nova evolução antes do primeiro snapshot e confirmou que ela **não foi perdida**. Testes Python e HTTP conferiram cursor vazio/monotônico e que a rota continua restrita ao proprietário. Os lotes posteriores permanecem limitados a 20 páginas de 500 eventos por atualização: um volume muito grande de eventos novos pode levar mais de um ciclo para ser percorrido.

Foi também corrigido o texto de Memórias que mencionava um preview remoto inexistente. A UI agora descreve o banco local; o servidor continua restrito a loopback, sem mudar sua política de segurança.

## Suítes e pacote

Na árvore atual, passaram **82 testes Python** e `npm run test:evolution`, `npm run test:pagination` e `npm run test:browser`, além do cenário Python de evolução com relógio simulado. O teste geral usa vídeo de padrão neutro e libera autoplay por flag; isso não valida reprodução do SL-001 ou autoplay normal. Não houve nova medição de cobertura. A execução e a falha esperada antes do reparo estão em [area-evolutiva.log](area-evolutiva.log).

Antes das correções desta etapa, a cópia do ZIP da revisão anterior foi extraída e testada: **74 arquivos, 73 hashes internos conferidos, 80 testes Python e as três suítes de navegador passaram**. Isso era uma verificação local, não independente. O pacote atualizado após as correções exige sua própria conferência; seu resultado é apresentado na resposta de entrega.

Para reproduzir na mesma máquina, sem expor o servidor:

```bash
cd tamagochi-module
python3 app.py
# Abrir http://127.0.0.1:8765 na mesma máquina e ler o arquivo owner.token
# cujo caminho o processo informa; não compartilhar o conteúdo.
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 tests/evolution_scenario.py
npm ci
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:pagination
CHROME_BIN=/caminho/para/chromium npm run test:browser
```

## Pendências e limites

- Não se pode demonstrar o SL-001 definitivo em movimento sem os vídeos/posters aprovados. O habitat mostra o aviso de ausência, não um slime substituto.
- Player/especificação F8, F9 e autoplay sob política normal com os arquivos reais não foram validados. A integração Muse Android é **futura**, não requisito para o fluxo web demonstrado; não há teste em Android físico ou com leitor de tela.
- Não há preview remoto da versão protegida: servidor e navegador devem estar na mesma máquina. Isso limita a demonstração direta neste sandbox, mas não exige abrir o serviço à rede.
- O Drive estava conectado, mas `Muse-REA` não foi localizado; nenhum backup remoto, upload ou acesso independente foi verificado. O ZIP local não inclui o banco de execução nem equivale a backup.
