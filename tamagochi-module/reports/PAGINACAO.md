# Paginação local da jornada · 28/10/2026

> Na revisão final posterior, páginas atrasadas de Memórias/Diário após exclusão ou nova atividade foram reproduzidas e descartadas quando obsoletas; página e total de Memórias passaram a usar uma transação. Veja [REVISAO_FINAL.md](REVISAO_FINAL.md). Não há garantia de sincronização instantânea entre abas.

> Revisão posterior: o botão de XP agora preserva o foco por teclado e informa a expansão em uma região de status; ações do habitat e conversa também receberam reparo localizado de foco. O uso de `aria-disabled` inclui uma guarda contra ativação repetida. Veja [`JORNADA_E_ACESSIBILIDADE.md`](JORNADA_E_ACESSIBILIDADE.md). As evidências de paginação abaixo são preservadas como registro da revisão anterior; não houve teste com leitor de tela.

## Causa reproduzida

Na versão anterior, com **122 concessões** em um banco descartável, o primeiro “Mostrar mais” carregava **20 → 40** itens, mas deixava o botão desabilitado e gerava `Cannot set properties of null (setting 'disabled')`. O manipulador guardava `event.currentTarget` somente por meio do evento e tentava acessá-lo no `finally` depois de um `await`: terminado o despacho, `currentTarget` já era `null`. Os controles equivalentes de Memórias e histórico de autonomia tinham o mesmo padrão.

Havia uma segunda falha independente: `refreshSnapshot` sempre solicitava a primeira página de XP e substituía a lista expandida. Depois de Descansar, ela voltava a **20** itens. A API confirmou que as 122 concessões anteriores permaneciam no SQLite; não era exclusão dos registros. A recarga também recriava a página sem guardar quantos itens haviam sido expandidos.

## Correção

- `web/app.js`: os três manipuladores capturam o botão antes do `await` e o reabilitam em `finally`, inclusive após falha. A leitura de mais XP é ordenada com as atualizações já existentes; erros não bloqueiam a próxima tentativa.
- `pet/service.py` e `app.py`: a página de `/api/awards` e seu `total` são lidos na **mesma transação**. A resposta ganhou o campo `total`; o formato dos itens, ordenação, limite de até 500 por requisição e autenticação de proprietário foram preservados. Não houve migração nem alteração dos registros.
- A janela da jornada mantém os itens carregados durante atualizações. Como o ledger de XP não oferece exclusão individual e recebe novas concessões no início, a janela cresce pelo número de concessões novas para manter os itens anteriores. Se o total mudar entre páginas de uma leitura, a janela é refeita; a leitura usa múltiplas páginas quando necessário.
- Para recarregar na mesma aba, a interface guarda em `sessionStorage` **apenas duas contagens**: itens carregados e total conhecido. Os itens são obtidos novamente da API autenticada; não são armazenados texto, IDs de eventos ou credenciais. Se o armazenamento estiver indisponível, o botão e atualizações na página aberta continuam funcionando, mas após recarga a lista volta à primeira página.

O conserto do botão também cobre Memórias e Diário; a restauração de suas listas após recarga não foi alterada. A restauração da jornada pressupõe o mesmo ledger não substituído/resetado. A política de voltar automaticamente à tela anterior, restaurar a posição exata da rolagem ou manter preferências entre sessões/abas **não estava especificada e foi deixada intacta**: a recarga continua abrindo Meu slime. `sessionStorage` é estado local da aba, sujeito ao comportamento e às permissões do navegador, não é backup.

## Regressões locais

`npm run test:pagination` executa `tools/inspect-pagination.cjs`, com Chromium e bancos descartáveis. Na execução registrada:

- Histórico de XP: **20 → 40 → 60 → 80 → 101 → 102 → 124 → 125** itens, incluindo erro de rede seguido de nova tentativa, resposta antiga atrasada, ação sobreposta, concessão feita em outra aba antes da recarga e expansão até o fim. Os identificadores das concessões anteriores foram comparados; nenhuma foi perdida ou duplicada.
- Uma janela de **520 → 521** itens foi reconstruída e recarregada em mais de uma página da API; uma escrita entre páginas provocou nova leitura. Para alcançar esse tamanho foram acrescentadas 450 linhas **sintéticas somente no banco temporário**: não demonstram progressão real do pet.
- Com `sessionStorage` bloqueado, foi mantida a paginação durante atualizações na página aberta e foi verificado o retorno seguro a 20 itens após recarga.
- Controles com a mesma causa: Memórias **100 → 200 → 300**, histórico de autonomia **20 → 40 → 45**. Foram produzidos por ações locais em banco descartável.
- A contagem de `/api/awards`, inclusive em página vazia além do fim, foi acrescentada a `tests/test_http_media.py`.

Nesta revisão passaram **78 testes Python**, `test:browser`, `test:evolution` e **duas execuções** de `test:pagination`. `compileall` e `node --check` passaram. O teste geral de navegador usa vídeo neutro e autoplay forçado; não comprova reprodução do SL-001 nem paridade com F8. Resultados e comandos completos: [`paginacao.log`](paginacao.log). Não foi medida nova cobertura nem feita auditoria independente.

## Reprodução

```bash
cd tamagochi-module
python3 -m unittest discover -s tests -v
npm ci
CHROME_BIN=/caminho/para/chromium npm run test:pagination
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:browser
```

Não houve dependência de F8/F9, mídia aprovada, Drive ou dispositivo físico. A integração com Muse Android continua futura e fora do escopo desta correção. As mídias SL-001 e F8/F9 reais, autoplay normal, leitor de tela e Android físico permanecem sem validação; o backup em `Muse-REA` não foi localizado ou verificado. ZIP e hashes locais não comprovam acesso independente ou backup remoto.
