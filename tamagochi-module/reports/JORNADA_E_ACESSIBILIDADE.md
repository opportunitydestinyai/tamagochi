# Minha jornada e Meu slime · inspeção local

**28/10/2026.** Este é o protótipo web local e independente; não é o aplicativo Muse integrado. A inspeção e as regressões usaram Chromium, servidor autenticado e bancos SQLite descartáveis. Os resultados abaixo são evidência textual local, não auditoria independente nem teste com leitor de tela.

## Mapa das telas e fluxo

1. **Meu slime** abre inicialmente. Mostra o habitat, humor, nível e estágio, XP neste nível e acumulado, felicidade, energia, vínculo, traços e momentos recentes. **Ver todos** abre os seis atributos; **Personalizar** oferece camadas e ajustes locais. Sem as mídias originais aprovadas, o habitat informa “O SL-001 vai aparecer aqui / Adicione a mídia original aprovada”: não está exibindo o personagem definitivo.
2. Ainda em **Meu slime**, **Ver jornada** abre **Minha jornada**; a navegação principal também permite entrar diretamente e voltar a **Meu slime**. Na jornada aparecem estágio e nível atuais, a linha de estágios e recompensas, tendências/especialização e o histórico das concessões de XP. A barra e o total de XP ficam em Meu slime; as concessões que ajudam a explicar esse total aparecem na jornada.
3. **Diário** mostra lembranças, atividades locais manuais e histórico de autonomia. **Memórias** permite consultar e apagar registros do pet; o ledger técnico de XP e deduplicação permanece. O texto da conversa não é armazenado pelo protótipo. Estes controles adicionais não foram todos auditados por teclado ou leitor de tela nesta revisão.
4. As ações do habitat atualizam o mesmo estado local que alimenta as duas telas. As recompensas de estágio são camadas de habitat/emblemas, não uma mudança de espécie ou rosto. A especialização é uma tendência independente do nível e não restringe as funções do agente.

## Estados observados

| Estado | Observação no navegador |
|---|---|
| **Vazio** | Banco novo: XP 0, nível 01, Despertar, “Em formação”; a jornada mostra “As concessões de XP vão aparecer aqui.” e não mostra o botão de paginação. |
| **Com registro** | Após **Brincar**, no mesmo banco: XP 5; a jornada mostra “Primeira interação do dia / 2026-10-28 / +5 XP”. Com apenas um item, “Mostrar mais” continua oculto. |
| **Expandido** | Fixture com dias simulados: XP 805, nível 05, Descoberta, Pesquisador e 122 concessões. A jornada começa com 20 itens; **Mostrar mais** leva a 40, depois às páginas seguintes. Ao fim, os 122 estão presentes e o botão fica oculto. A fixture não representa tempo real nem dados de uma pessoa. |
| **Após recarga** | Na mesma aba, com `sessionStorage` disponível e o mesmo ledger, a recarga volta a **Meu slime**; ao reabrir Minha jornada, os 40 itens já expandidos voltam a ser buscados da API. A tela anterior e a posição de rolagem **não** são restauradas. Se o armazenamento da aba estiver bloqueado, a recarga volta à primeira página; a expansão ainda funciona enquanto a página está aberta. |

A API lê página e total na mesma transação. A janela expandida também se ajusta quando concessões novas aparecem no início, preservando as anteriores. Não são guardados IDs, conteúdo ou credenciais em `sessionStorage`, apenas as contagens necessárias para a recuperação na aba; isso não é backup.

## Ações e progressão demonstradas

Com regras padrão e um banco novo, o teste de navegador percorreu as seguintes ações; os atributos estão na ordem **felicidade / energia / curiosidade / conhecimento / vínculo / confiança**:

| Ação | XP acumulado | Atributos observados |
|---|---:|---|
| Inicial | 0 | 75 / 80 / 50 / 10 / 20 / 50 |
| Brincar | 5 | 83 / 70 / 50 / 10 / 23 / 51 |
| Descansar | 5 | 83 / 90 / 50 / 10 / 23 / 51 |
| Explorar | 5 | 85 / 82 / 55 / 10 / 23 / 51 |
| Aprender | 13 | 85 / 75 / 57 / 14 / 23 / 51 |
| Criar | 21 | 88 / 68 / 59 / 14 / 23 / 51 |
| Conversar, mensagem considerada significativa | 23 | 90 / 68 / 59 / 14 / 25 / 52 |

Esses valores são de uma sequência específica, sujeitos às regras, energia, deduplicação e limites diários; não significam que toda ação sempre conceda o mesmo XP. Na configuração padrão, “significativa” é uma aproximação por comprimento mínimo de 30 caracteres, não compreensão semântica. A resposta é local e pré-definida; o texto não é enviado nem persistido.

O XP necessário para atingir o nível `n` é `arredonda_metade_para_cima(100 × (n−1)^1,5)` por padrão. Exemplo: 150 XP acumulados significam nível 2, **50/183 XP** no nível e **27,3%** na barra. Em outra fixture com dias simulados, **Criar** passou de 797 para 810 XP, atingiu o nível 5, mostrou o estágio **Descoberta** e uma notificação; o estágio persistiu na recarga. A notificação/solicitação de milestone não comprova reprodução do vídeo aprovado, que não estava disponível.

## Lacunas reproduzidas e reparo localizado

Antes da mudança, ao ativar **Ver jornada** por Enter, o foco ia para `BODY` ou permanecia no botão da tela agora oculta. Ao ativar **Mostrar mais**, o botão nativamente desabilitado expulsava o foco para `BODY`, inclusive quando a última página fazia o botão desaparecer. A jornada não tinha região própria para informar a expansão. A mesma perda de foco foi reproduzida com Enter em Brincar, Descansar, Explorar, Aprender, Criar e no botão de envio da conversa.

Agora:

- Ao sair de uma tela por um atalho dentro dela, o título da tela aberta recebe foco; ao usar a navegação persistente, o foco não é forçado para outro lugar. A tela selecionada mantém `aria-current="page"`.
- Na paginação de XP, o botão tem nome específico e `aria-controls`. Durante a solicitação fica com `aria-disabled="true"` e continua focável; uma guarda em código impede um segundo pedido. Em falha, o estado ocupado é removido, o foco permanece e o erro aparece na região de notificações.
- Se o foco ainda estiver no botão quando a página chega, ele passa ao **primeiro registro recém-carregado**, inclusive no fim. Uma região `role="status"`, `aria-live="polite"` recebe, por exemplo, “20 registros de XP carregados. Mostrando 40 de 122.” ou “Todos os 122 registros de XP foram carregados.” Os registros focados têm nome acessível e contorno de foco visível.
- Se a pessoa mudar o foco ou sair da jornada durante a espera, o carregamento não o toma de volta. Uma atualização sem alterações não recria o item focado; se uma concessão nova entrar no começo, o mesmo registro focado é localizado por evento e motivo.
- Nas cinco ações diretas e no envio da conversa, o estado de espera também preserva o foco e uma guarda evita ativação duplicada enquanto o pedido está pendente. A resposta não move o foco se a pessoa já tiver ido a outro controle.

Essas verificações usam Tab/Enter em Chromium. A árvore de acessibilidade do navegador expõe o botão como indisponível durante a leitura, seu nome, o registro focado e a região de status. Isso **não garante como um leitor de tela anunciará** tais elementos e não é uma declaração de conformidade ou de acessibilidade completa do aplicativo.

## Arquivos e trechos que sustentam o relato

- `web/index.html`: atalho `data-go="evolution"`, as quatro seções, as ações do habitat e o histórico. O botão de XP usa `aria-label="Mostrar mais registros de XP" aria-controls="award-list"`; a região `#award-announcement` usa `role="status" aria-live="polite" aria-atomic="true"`.
- `web/app.js`: `setView()` identifica quando o foco estava em uma seção que acabou oculta; `renderState()` alimenta habitat e jornada; `renderAwardList()` preserva o foco de um registro em atualizações. `beginButtonOperation()` marca o controle ocupado e bloqueia reentrada; o handler de `#load-more-awards` escolhe o primeiro item novo apenas se o foco ainda estava no botão. `action()` e o formulário de chat usam a mesma guarda. A leitura de janela e o armazenamento por aba permanecem separados dessa correção.
- `web/styles.css`: `.sr-only`, contorno `:focus-visible` para título/registro e aparência de espera para os controles com `aria-disabled`.
- `pet/service.py`, `pet/repository.py` e `app.py`: regras, persistência e endpoint de páginas/total; não houve alteração neles nesta revisão.
- `tools/e2e-evolution.cjs` e `tools/inspect-pagination.cjs`: navegação, Tab/Enter, repetição enquanto ocupado, falhas, foco movido durante espera, árvore de acessibilidade, estados e recarga. `tools/browser-test-helpers.cjs` retém a entrega de uma resposta já produzida pelo servidor **somente no navegador de teste**.

## Resultados e reprodução

Nesta revisão passaram localmente **78 testes Python**, `npm run test:evolution`, `npm run test:pagination` e `npm run test:browser`; também passaram `compileall` e `node --check`. Os testes de evolução/paginação usam bancos temporários e não importam mídia do pet nem usam a ponte. O teste geral usa vídeo de padrão neutro e uma flag que libera autoplay; não valida autoplay normal ou reprodução do SL-001. O histórico **520 → 521** é uma fixture sintética de paginação, não evolução real. Nenhuma nova cobertura foi medida.

Durante o desenvolvimento, o antigo interceptador CDP de teste deixou de capturar respostas em algumas execuções paralelas. A instrumentação foi trocada por uma trava de entrega de resposta no navegador de teste e as suítes acima passaram depois; a falha e as execuções estão registradas em [`jornada-acessibilidade.log`](jornada-acessibilidade.log). Também há exemplos antes/depois, inclusive as falhas esperadas das novas regressões.

```bash
cd tamagochi-module
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 tests/evolution_scenario.py
npm ci
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:pagination
CHROME_BIN=/caminho/para/chromium npm run test:browser
```

Não houve teste com leitor de tela ou Android físico, nem validação das mídias reais, do player F8/F9 ou da integração Muse Android. O backup integral no Drive continua pendente: `Muse-REA` não foi localizado na conta acessível. O ZIP e os hashes conferidos localmente não provam acesso independente nem entrega remota. Nenhuma decisão sobre restaurar tela/rolagem, integração futura ou pendências externas foi alterada.
