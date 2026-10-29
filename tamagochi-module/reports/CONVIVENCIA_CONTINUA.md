# Conversa e convivência contínua · inspeção local

**28/10/2026.** A avaliação usa o protótipo web independente, Chromium, processos Python locais e bancos SQLite descartáveis. Não usa dados de uma pessoa, mídias aprovadas do SL-001 nem Muse F1–F9. Os resultados abaixo são observações locais, não uma auditoria independente.

**Conclusão:** XP, atributos, vínculo, confiança, traços, tendência e registros genéricos são conservados no mesmo banco entre sessões. Nível e estágio são recalculados a partir do XP e da configuração. Humor e energia também são persistidos, mas podem mudar com o tempo ao consultar o estado. Nas sequências verificadas, as telas corresponderam ao estado retornado pelo servidor; não foi reproduzida divergência de interface que justificasse alterar o comportamento do produto nesta revisão. Foram acrescentados apenas testes e documentação.

## Onde vive cada informação

| Informação | Comportamento observado ou implementado |
|---|---|
| XP e concessões | `pet.state_json` contém o XP acumulado; `xp_awards` registra motivo, valor e dia. Transações também registram IDs para deduplicação. A continuidade depende de reabrir **o mesmo banco**. |
| Nível e estágio | São derivados de XP e configuração na resposta pública, não campos independentes restaurados de outra tela. O padrão atinge o nível 5 com 800 XP; o estágio passa a Descoberta. |
| Atributos e vínculo | Felicidade, energia, curiosidade, conhecimento, vínculo e confiança ficam no estado persistido. As mudanças são limitadas a 0–100. Energia recebe recuperação temporal, de modo que não precisa ser idêntica ao valor salvo no instante anterior. |
| Humor | O humor e o sinal recente são gravados, mas o motor reconcilia o tempo e recalcula o humor ao consultar o estado. Por padrão o sinal dura 20 minutos; a energia recupera 0,5 ponto por hora, com até 24 horas consideradas por reconciliação. A autonomia vem desligada; a recuperação temporal não depende de ativá-la. |
| Traços e especialização | Traços, pontuações e especialização ficam no estado. As pontuações são atualizadas pelas atividades; a especialização é uma tendência independente do estágio. |
| Conversa | A interface mantém o conteúdo enquanto o diálogo está aberto. O envio normal não manda o texto ao servidor: manda a ação, um ID e um booleano baseado no comprimento. O banco registra uma memória genérica, não a transcrição. Fechar o diálogo limpa entrada e saída visíveis e impede que uma resposta atrasada as restaure. Uma operação pendente pode manter uma cópia temporária em memória até terminar; não é garantia de apagamento seguro do navegador ou do sistema. |
| Telas | Na mesma aba, `renderState()` usa a mesma variável para Meu slime, detalhes dos atributos e Minha jornada. Diário e Memórias consultam listas de registros. Uma atualização após escrita reconsulta o servidor. Entre abas/sessões há banco compartilhado, mas não há garantia de atualização instantânea ou de um snapshot global atômico entre endpoints; o código atualiza a aba visível periodicamente e ao retornar à visibilidade. |

A sessão e as credenciais locais são mantidas em memória do processo e mudam ao reiniciar. Isso não apaga o estado se o mesmo diretório de dados for reutilizado. Uma instalação nova, outro banco ou perda dos arquivos não recupera os dados automaticamente; o ZIP de código não é backup do banco de execução.

## Trechos de implementação

`pet/repository.py` cria `pet(state_json, config_json)`, concessões, eventos e memórias e só cria o SL-001 se não existir. As alterações são feitas sob `BEGIN IMMEDIATE`, com `commit`/`rollback`. Em `pet/service.py`, o snapshot reconcilia e persiste antes de produzir a resposta; nível e estágio são calculados:

```python
# pet/service.py · snapshot e resposta pública, trechos
self._reconcile(state, config, now)
self._finish(conn, before, state, config, now)
return self._public(state, config)

progress = ExperienceEngine.progress(state["xp"], config)
result["level"] = progress["level"]
result["stage"] = EvolutionEngine.stage(result["level"], config)
```

A reconciliação e as regras padrão podem ser inspecionadas em `pet/service.py:91–99` e `pet/model.py:52–77,229–247`. A recuperação é limitada, e a prioridade de energia baixa pode fazer o humor ficar **Cansado** mesmo após um marco de evolução.

O chat não analisa o significado do texto. A interface usa o tamanho do texto após `trim()` para decidir o booleano. O padrão é 30 **unidades UTF-16 do JavaScript**, que não são necessariamente 30 caracteres visíveis; a API recebe o booleano e não verifica o comprimento por não receber o conteúdo:

```js
// web/app.js · somente campos enviados à API pelo formulário normal
json: {action:'CHAT', eventId:eventId('chat'),
       meaningful:text.length >= (state?.rules?.meaningfulChatMinChars ?? 30)}

// A resposta incorpora apenas o humor e a energia do resultado local.
reply.textContent = `Estou ${String(labels.mood[result.state.mood] || 'tranquilo').toLowerCase()} e tenho ${Math.round(result.state.energy)} de energia. Obrigado por este momento! Esta é uma resposta local pré-definida.`;
```

A implementação completa está em `web/app.js:474–497`. `app.py:297–300` aceita apenas `action`, `eventId` e `meaningful` nessa rota. `pet/service.py:25–33,176–214` grava o texto genérico “Uma interação foi registrada, sem guardar o texto da conversa.” e aplica os efeitos; não recebe a transcrição. O processamento é local e determinístico, sem LLM ou compreensão semântica da mensagem.

Com regras padrão, cada CHAT aceito adiciona felicidade +2, vínculo +2 e confiança +1, respeitando o teto dos atributos; incrementa o traço SOCIAL e a pontuação COMPANION. A primeira interação do dia pode conceder 5 XP, mesmo se o chat for curto; mensagens classificadas pelo comprimento podem conceder mais 2 XP, no máximo três concessões de conversa/dia e sujeitas ao teto diário total de 120. Após os limites de XP, uma nova ação com ID diferente ainda pode alterar atributos. Repetir **o mesmo ID de evento** é diferente de reenviar uma nova mensagem e não duplica a ação.

`web/app.js:96–135,273–290,511–512` usa o mesmo `state` em habitat e jornada, obtém `/api/state` e atualiza a página visível a cada 60 segundos e ao voltar à visibilidade. No teste entre contextos, a comparação foi feita depois de uma atualização explícita; não foi cronometrado nem garantido o intervalo de atualização automática entre abas.

## Evidência no navegador: conversa, telas e sessões

`tools/e2e-evolution.cjs:119–160,373–487` executou estas ações com banco novo e regras padrão. Os atributos abaixo são exibidos na ordem **felicidade / energia / curiosidade / conhecimento / vínculo / confiança**, arredondados como na interface:

| Etapa observada | XP; nível; estágio; humor | Atributos |
|---|---|---|
| Início | 0; 1; Despertar; Tranquilo | 75 / 80 / 50 / 10 / 20 / 50 |
| Conversa curta `Oi!` | 5; 1; Despertar; Tranquilo | 77 / 80 / 50 / 10 / 22 / 51 |
| Mais uma conversa acima do limiar | 7; 1; Despertar; Tranquilo | 79 / 80 / 50 / 10 / 24 / 52 |
| Depois de Brincar | 7; 1; Despertar; Empolgado; tendência Companheiro | 87 / 70 / 50 / 10 / 27 / 53 |
| Bloquear e entrar novamente no mesmo processo | 7; 1; Despertar; Empolgado; Companheiro | 87 / 70 / 50 / 10 / 27 / 53 |
| Outra sessão envia conversa curta; primeira sessão atualizada | 7; 1; Despertar; Empolgado; Companheiro | 89 / 70 / 50 / 10 / 29 / 54 |
| Novo processo e nova sessão, mesmo SQLite | 7; 1; Despertar; Empolgado; Companheiro | 89 / 70 / 50 / 10 / 29 / 54 |

O teste compara habitat, detalhes dos seis atributos e jornada com o estado renderizado e com `/api/state`, incluindo sinal de humor, traços e pontuações. A energia não arredondada pode recuperar um pequeno valor durante as leituras, de acordo com o relógio real. Diário e Memórias mostraram o registro genérico; a jornada mostrou as duas concessões. A primeira interação diária já tinha sido consumida quando a outra sessão enviou o chat curto, portanto ela alterou os atributos sem aumentar XP.

Duas mensagens diferentes com o mesmo humor e energia produziram a mesma resposta pré-definida. O teste capturou os dois corpos normais de `/api/actions`, verificou que continham somente os três campos permitidos e que não continham um marcador sintético; verificou que o marcador aparecia no diálogo aberto, desaparecia ao fechar/reabrir e não aparecia nas respostas de memórias, concessões ou eventos. Depois do encerramento limpo do servidor, procurou o marcador em `pet.sqlite3` e em seus arquivos `-wal`/`-shm`, quando presentes. A verificação é desse fluxo e marcador de teste, não uma garantia sobre extensões, ferramentas do navegador ou todo o sistema operacional.

O novo processo abre o mesmo diretório, gera outra credencial e exige novo login. O encerramento testado foi limpo por SIGINT, não simula queda de energia ou corrupção. A segunda sessão do navegador usa contexto separado; a sincronização da primeira é explicitamente solicitada antes da comparação.

## Evolução produzida por conversa e persistida

Outra fixture descartável foi preparada por ações com **dias de relógio simulado**, não por usuários nem por espera real. Na abertura do servidor, a energia foi reconciliada com a regra de recuperação limitada. Na UI autenticada:

```text
Antes:   797 XP · nível 4 · Despertar  · Cansado · vínculo 71 · confiança 75
CHAT:    804 XP · nível 5 · Descoberta · Cansado · vínculo 73 · confiança 76
Restart: 804 XP · nível 5 · Descoberta · Cansado · vínculo 73 · confiança 76
```

O chat elegível recebeu 5 XP pela primeira interação do dia e 2 pelo critério de comprimento, cruzando o limiar de 800 XP. A jornada indicou Descoberta, a UI mostrou a notificação e a especialização Pesquisador permaneceu. A resposta dizia “Estou cansado...” e refletiu a energia retornada pelo motor; nenhuma mídia aprovada foi reproduzida. Após encerramento limpo do servidor, outro processo e nova autenticação com o mesmo banco preservaram o estado e a linha de estágio:

```js
// tools/e2e-evolution.cjs · trechos do teste
assert.deepEqual([evolved.xp, evolved.level, evolved.stage.key], [804, 5, 'DISCOVERY']);
await closeServer(entry, {preserveData:true});
restarted = await serverFor(null, entry.directory);
// abre a página e autentica com a nova credencial
assertContinuous(evolved, await sharedState(page));
```

## Relógio simulado, deduplicação e validação HTTP

`tests/test_engine.py:101–127` recria o motor usando o mesmo SQLite e um relógio fixo após Brincar e CHAT elegível. XP 7, nível 1, Despertar, humor EXCITED, atributos `85/70/50/10/25/52`, sinal, traços e pontuações permanecem. Um retry com o mesmo ID de CHAT não concede XP nem altera o vínculo ou cria outra memória. Ao avançar **21 minutos simulados**, o sinal expira, o humor passa a CALM e a energia passa de 70 para 70,175; XP e os outros atributos permanecem. Não se esperou 21 minutos reais e esse teste recria o motor, não o processo:

```python
self.clock.advance(minutes=21)
later = restarted.snapshot(run_due=False)
self.assertEqual((later['mood'], later['recentSignal']), ('CALM', None))
self.assertEqual(later['energy'], 70.175)
```

`tests/test_engine.py:201–206` verifica o limite de três concessões de CHAT: seis eventos elegíveis geram 5 + 3×2 = 11 XP no mesmo dia. O novo `tests/test_http_media.py:100–109` envia deliberadamente um campo sintético `text` por HTTP e verifica rejeição 400, sem alterar XP, atributos, memórias ou concessões. Isso testa o contrato da rota; não significa que o servidor nunca possa receber um corpo malformado enviado por um cliente diferente da UI.

## Resultados, reprodução e limites

Execução local desta revisão: **80 testes Python aprovados**, `npm run test:evolution`, `npm run test:pagination` e `npm run test:browser` aprovados; o cenário Python com dias simulados também passou. O log está em [`convivencia-continua.log`](convivencia-continua.log). Não foi feita nova medição de cobertura. Na primeira tentativa o cenário foi executado sem `PYTHONPATH` e falhou ao importar `pet`; reexecutado com o comando documentado abaixo, passou.

```bash
cd tamagochi-module
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 tests/evolution_scenario.py
npm ci
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:pagination
CHROME_BIN=/caminho/para/chromium npm run test:browser
```

Os testes de evolução e paginação não usam mídia do personagem nem eventos da ponte. O teste geral usa vídeo neutro e libera autoplay por flag; não valida a política normal de autoplay. Não houve teste com leitor de tela, Android físico, integração Muse Android, player F8/F9 ou mídias reais do SL-001. O Drive permanece pendente porque `Muse-REA` não foi localizado; não houve upload nem comprovação independente de entrega ou acesso remoto.
