# Experiência observada e correção de XP

**Revisão local:** 28/10/2026 · protótipo 0.1.0. As evidências abaixo foram produzidas neste ambiente, com bancos descartáveis e dados fictícios; não são verificação independente de entrega, Drive ou links. O relógio foi avançado artificialmente nos cenários que mostram evolução em vários dias.

## 1. Telas realmente observadas

As capturas foram feitas no Chromium, a partir da interface servida em loopback, sem importar nenhuma mídia do personagem. O cenário gráfico é só um ambiente; o SL-001 aprovado **não aparece** porque seus vídeos/posters não foram disponibilizados.

| Captura local | Conteúdo |
|---|---|
| [01 · visão inicial](evidencias-experiencia/01-visao-inicial.png) | Habitat com aviso de mídia ausente; nível 1, Despertar, 0 XP, humor Tranquilo, atributos principais e as seis ações. |
| [02 · após brincar](evidencias-experiencia/02-apos-brincar.png) | Feedback visual, humor Empolgado, felicidade 83, energia 70, vínculo 23 e 5 XP no primeiro dia. |
| [03 · progresso no nível 2](evidencias-experiencia/03-nivel2-150xp.png) | Estado preparado por ações com dias simulados: 150 XP acumulados, 50/183 no nível e 133 restantes. |
| [04 · jornada no nível 5](evidencias-experiencia/04-jornada-descoberta.png) | Descoberta marcada como atual, Despertar desbloqueado, etapas futuras bloqueadas, tendência Pesquisador e histórico de XP. |

A tela principal (`web/index.html:61–103`) mostra humor, nível, estágio, XP, felicidade, energia, vínculo, traços e ações. **Ver todos** abre os seis atributos; **Minha jornada** mostra os seis estágios, recompensas, especialização e histórico. **Diário** apresenta atividades locais; **Memórias** permite consultar e apagar registros. O estado inicial interno é nível 1, XP 0, felicidade 75, energia 80, curiosidade 50, conhecimento 10, vínculo 20, confiança 50, `CALM` e `IDLE`; `IDLE` não é mostrado como rótulo nessa tela.

## 2. Ações e seus efeitos

Efeitos padrão em `pet/model.py:55–67` e `config.example.json`; atributos são limitados a 0–100 e uma ação com energia insuficiente não é concluída.

| Ação | Alteração padrão | Resultado observado |
|---|---|---|
| Brincar | felicidade +8, energia −10, vínculo +3, confiança +1 | Registro de atividade; se for a primeira interação do dia, +5 XP. |
| Descansar | energia +20 | Recuperação imediata. |
| Explorar | curiosidade +5, energia −8, felicidade +2 | Tema de uma lista local, sem pesquisa externa. |
| Aprender | conhecimento +4, energia −7, curiosidade +2 | Informação de lista local e até +8 XP por ação elegível. |
| Criar | felicidade +3, energia −7, curiosidade +2 | Ideia de lista local e até +8 XP por ação elegível. |
| Conversar | felicidade +2, vínculo +2, confiança +1 | Resposta pré-definida; conversa com pelo menos 30 caracteres dá até +2 XP, sujeita ao limite. Texto não é enviado nem persistido. |

No teste de navegador, as seis ações foram executadas sequencialmente. Primeiro **Brincar** alterou felicidade 75→83, energia 80→70, vínculo 20→23, confiança 50→51 e XP 0→5. Em seguida, **Descansar**, **Explorar**, **Aprender**, **Criar** e uma conversa significativa resultaram em felicidade 90, energia 68, curiosidade 59, conhecimento 14, vínculo 25, confiança 52 e 23 XP. O cenário Python reproduz os estados intermediários no log. Os valores de XP dependem dos limites por dia e da configuração; não são ganho garantido em toda repetição.

## 3. Regras de evolução e evidência

- Limiar acumulado para o nível `n`: `arredonda_metade_para_cima(100 × (n − 1)^1,5)` na configuração padrão. Para níveis 1–6, os limiares são 0, 100, 283, 520, 800 e 1.118 XP. `pet/model.py:188–223` calcula limiares, nível e progresso.
- Ganhos locais padrão: primeira interação +5 XP uma vez ao dia; conversa significativa +2 (até 3/dia); Aprender +8 (até 5/dia); Criar/experimento +8 (até 5/dia). Teto global: 120 XP/dia. A regra de conversa é uma aproximação por tamanho, não compreensão semântica.
- As faixas são **Despertar 1–4, Descoberta 5–9, Aprendizado 10–19, Companheiro 20–34, Explorador 35–49 e Evoluído 50+**. As recompensas são camadas ambientais/emblemas, sem redesenhar ou substituir o personagem.
- Especialização é independente do nível, baseada em contagens de atividades; por padrão, precisa de 3 ações e preserva a líder em empate.
- O cenário `tests/evolution_scenario.py` usou apenas ações locais e datas simuladas. Chegou a 100 XP/nível 2 no segundo dia simulado, 150 XP no mesmo dia e 805 XP/nível 5 no nono. Registrou `PET_EVOLUTION_UNLOCKED` com `stage=DISCOVERY` e recompensa `Moldura de descoberta`. O pedido de `milestone_video` é apenas um evento: sem arquivo importado, não houve playback do personagem.

## 4. Lacuna identificada e correção

**Antes:** com 100 XP, o nível era 2 e a barra representava 0/183, mas o texto adjacente dizia `100 / 283 XP`. No Chromium isolado foram observados `100 / 283 XP`, barra `0%` e `183 XP para o próximo nível`. O numerador/denominador eram acumulados, mas a barra era relativa ao nível. Outro caso-limite da mesma apresentação ocorria quando o arredondamento chegava a 100% com 1 XP ainda faltando, por exemplo em 241.494 XP/nível 180 na fórmula padrão.

**Depois:** `web/index.html:79–84` nomeia a fração como **XP neste nível** e mostra o total em linha separada. `web/app.js:67–79` usa os campos retornados pelo motor, sem recalcular a fórmula nem alterar XP persistido:

```js
const {intoLevel, neededInLevel, nextThreshold, percent} = state.progress;
$('#xp-level-current').textContent = formatXP(intoLevel);
$('#xp-level-needed').textContent = formatXP(neededInLevel);
$('#xp-current').textContent = formatXP(state.xp);       // acumulado
$('#xp-next').textContent = formatXP(nextThreshold);     // próximo limiar acumulado
setBar('#bar-xp', percent);
```

O percentual derivado em `pet/model.py:218–226` agora é limitado a 99,9% enquanto restar XP; no limiar seguinte o nível avança e a barra recomeça em 0%. Isso muda apenas a apresentação derivada, não o cálculo de níveis ou os dados de XP. Com uma configuração fictícia de teste, o navegador verificou 2.367/2.368 XP, 1 restante e barra 99,9%, depois cruzou o nível e recarregou. A mesma fração é exposta em `role="progressbar"`, `aria-valuenow`, `aria-valuemax` e `aria-valuetext`; os atributos foram inspecionados no DOM, mas não houve teste com leitor de tela. Os IDs existentes do total/limiar foram mantidos.

| XP acumulado | Nível | XP neste nível | Barra | XP restante |
|---:|---:|---:|---:|---:|
| 0 | 1 | 0/100 | 0% | 100 |
| 100 | 2 | 0/183 | 0% | 183 |
| 150 | 2 | 50/183 | 27,3% | 133 |
| 283 | 3 | 0/237 | 0% | 237 |
| 800 | 5 | 0/318 | 0% | 318 |

O navegador também cruzou o nível por uma conversa local: **98→105 XP**, notificação de nível 2 e 5/183; a recarga preservou os valores. Em outro banco, uma escala configurada de 200 gerou 5/200 (2,5%) e persistiu após recarga. As fórmulas e faixas ficam bloqueadas após a concessão do primeiro XP, como antes.

## 5. Testes e reprodução

Registro completo local: [`experiencia-evolutiva.log`](experiencia-evolutiva.log). Nesta revisão passaram **77 testes Python** e dois testes de navegador: o geral preexistente e o novo `tools/e2e-evolution.cjs`. O novo cobre nível 1, seis ações e seus efeitos, transição local 1→2, 100/150 XP, arredondamento a 1 XP do próximo nível, estágio 5, estado ARIA, configuração alternativa, recarga e largura móvel. Chromium 153.0.8010.0, Node 22.22.3, Python 3.11.2. `compileall` e `node --check` também passaram. São resultados locais, não certificação independente.

```bash
cd tamagochi-module
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 tests/evolution_scenario.py
npm ci
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:browser
# Para reproduzir as capturas em um diretório novo:
CHROME_BIN=/caminho/para/chromium EVIDENCE_DIR=/tmp/evidencias-muse npm run test:evolution
```

O novo teste visual não importa mídia nem envia eventos pela ponte. O teste geral usa vídeo de cores **sem personagem** e força autoplay por flag; por isso não comprova autoplay sob a política normal. O cenário usa relógio simulado e bancos temporários, não vários dias reais.

## 6. Pendências

Mídias originais SL-001, player/especificação F8, integração F9, autoplay normal com os arquivos aprovados, acessibilidade com tecnologia assistiva e Android físico permanecem não validados. O Google Drive estava conectado, mas `Muse-REA` não foi localizada; o backup não foi enviado nem verificado. Não há preview remoto: o servidor protegido aceita somente loopback. Nenhuma dessas pendências foi tratada como concluída ou como bloqueio desta correção independente.
