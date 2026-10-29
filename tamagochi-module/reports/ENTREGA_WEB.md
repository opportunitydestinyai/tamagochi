# Entrega local · área Tamagotchi evolutiva

**29/10/2026.** Revisão do protótipo independente Python/SQLite e HTML/CSS/JavaScript, com dados descartáveis e Chromium headless. Nesta revisão não houve compilação de APK, publicação no GitHub ou integração com Muse Android; o registro descreve aquele momento.

## Telas e fluxos inspecionados

As quatro telas são seções de `GET /`, em `web/index.html`; a navegação e o estado exibido estão em `web/app.js`.

| Tela | Evidência observada | Captura local |
|---|---|---|
| **Meu slime** | Habitat, indicador de mídia ausente, humor, atributos e seis ações. Na sequência Brincar, Descansar, Explorar, Aprender, Criar e Conversar, o XP foi 0 → 5 → 5 → 5 → 13 → 21 → 23 e permaneceu 23 após recarga. | [Meu slime](evidencias-entrega/01-meu-slime.png) |
| **Minha jornada** | Nível, estágio, barra de XP, tendências e histórico. As cinco transições foram exercitadas no navegador e preservadas após recarga. | [Jornada em Evoluído](evidencias-entrega/02-minha-jornada.png) — cenário com dias simulados. |
| **Diário** | Os quatro geradores locais manuais foram executados com o agendamento desligado; o histórico persistiu após recarga. | [Diário](evidencias-entrega/03-diario.png) |
| **Memórias** | Consulta e exclusão de registros genéricos; a UI explica que IDs e concessões técnicas permanecem para deduplicação. | [Memórias](evidencias-entrega/04-memorias.png) |

A conversa é uma resposta pré-definida, não um agente generativo. O formulário não envia o texto ao servidor; uma operação pendente pode mantê-lo temporariamente na memória do navegador. Em outra sessão e após reiniciar o processo com o mesmo SQLite, estado e registros genéricos continuaram disponíveis. Ao retorno de visibilidade `hidden → visible`, simulado por minimizar/restaurar a janela no Chromium headless, a jornada atualizou de 0 para 5 XP após uma ação em outra página. Isso não é teste físico nem demonstra sincronização instantânea entre abas.

## Evolução

As regras estão em `pet/model.py` e as transações em `pet/service.py` / `pet/repository.py`. XP acumulado para nível `n`: `arredondar(100 × (n−1)^1,5)`. A especialização é independente do estágio, e as recompensas são camadas do ambiente, sem redesenhar o personagem.

| Transição na interface | XP observado antes → depois |
|---|---:|
| Despertar → Descoberta, nível 5 | 797 → 810 |
| Descoberta → Aprendizado, nível 10 | 2692 → 2705 |
| Aprendizado → Companheiro, nível 20 | 8275 → 8288 |
| Companheiro → Explorador, nível 35 | 19816 → 19829 |
| Explorador → Evoluído, nível 50 | 34293 → 34306 |

Os bancos avançados foram preparados com ações e **dias simulados**. O último caso usou 377 dias simulados, 5.987 ações e 13.396 eventos; não representa 377 dias de uso real. A decoração Constelação foi aplicada e permaneceu após recarga.

## Correção localizada nesta entrega

O teste reproduziu no Diário textos como `O humor do SL-001 agora é FOCUSED.` e `A tendência RESEARCHER se destacou nas atividades locais.`, enquanto o habitat e a jornada usavam “Concentrado” e “Pesquisador”. `web/app.js` agora apresenta esses registros com os mesmos rótulos em português nas telas Diário e Memórias, inclusive após recarga.

A mudança é **somente de apresentação**: códigos e registros persistidos continuam inalterados, sem migração; conteúdo que não corresponde exatamente aos formatos conhecidos permanece como está e continua escapado. A regressão cobre todos os nove rótulos de humor, cinco especializações, conteúdo desconhecido e os dois fluxos reais. Não foram alteradas regras de XP, evolução ou mídias. Capturas de relatórios anteriores foram preservadas e podem mostrar os códigos antigos.

## Testes executados localmente

- **83 testes Python** passaram no início desta revisão; nenhuma alteração Python foi feita depois.
- Após a correção de apresentação, passaram `test:evolution`, `test:pagination` e `test:browser` em Chromium 153. A suíte de evolução percorreu as quatro telas, ações, conversa, recarga, retorno de visibilidade e as cinco transições simuladas. A suíte de paginação cobriu os casos de exclusão e atividade concorrentes corrigidos na revisão anterior.
- A falha anterior e as saídas completas estão em [entrega-web.log](entrega-web.log). O teste geral usa vídeo neutro e força autoplay; não valida autoplay normal nem a reprodução de SL-001.

## Executar localmente

```bash
cd tamagochi-module
python3 app.py
```

Abra `http://127.0.0.1:8765` na **mesma máquina** e use o arquivo privado de proprietário cujo caminho aparece no terminal, sem compartilhar seu conteúdo. O servidor aceita apenas loopback; não há preview remoto seguro disponível neste ambiente. Para os testes, veja `README.md`.

## Limites e entrega

Não há APK nem implementação Android neste checkout; **nenhuma compilação de APK foi realizada**. A revisão descrita neste relatório ocorreu antes de qualquer eventual push posterior do código ou do ZIP. Muse Android é integração futura e não bloqueia a avaliação web. As mídias aprovadas do SL-001, player F8/F9 e autoplay normal não foram validados; nenhum teste físico Android foi feito. A pasta `Muse-REA` não foi localizada na revisão anterior e **não houve backup remoto no Drive**. O ZIP não contém banco real e sua integridade local não comprova acesso independente nem backup no Drive.
