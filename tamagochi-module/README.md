# Muse AI · Tamagotchi Evolution & Companion 0.1.0

SL-001 é a única identidade do pet. Este módulo é um protótipo separado: motor determinístico, banco SQLite, interface responsiva e ponte normalizada. Não implementa outro agente.

## Requisitos e execução

- Python 3.11+ e dados IANA de fuso horário disponíveis ao `zoneinfo`. Nenhuma instalação Python adicional é necessária.
- Navegador moderno com JavaScript; vídeo MP4/WebM depende do codec do navegador.

```bash
cd tamagochi-module
python3 app.py
# Abra http://127.0.0.1:8765
```

Opções:

```bash
python3 app.py --port 8766 --data-dir /caminho/privado/muse-pet
# Personalize config.example.json, depois use-o somente na criação de um banco novo:
python3 app.py --data-dir /caminho/novo --config config.example.json
```

`--config` é validado e aplicado **apenas ao criar** o pet; nunca sobrescreve um banco existente. Ajustes posteriores são salvos em Configurações → Regras avançadas ou via `POST /api/config` autenticado. O processo deve estar ativo para que a interface funcione, mesmo sem internet. Não há service worker, APK ou serviço nativo Android.

O servidor permite apenas `127.0.0.1`/`localhost`, rejeita `--host 0.0.0.0` e não suporta proxy nem preview remoto. Na inicialização gera dois tokens aleatórios diferentes e indica no terminal os **caminhos** dos arquivos privados `owner.token` e `bridge.token`, dentro de `data/.access/session-.../`. Abra a interface na mesma máquina e copie o conteúdo de `owner.token` para a tela de desbloqueio. Não envie o conteúdo por chat, não o coloque em URL, logs, repositório ou backup. Em POSIX, os arquivos têm modo `600` e o diretório da sessão, `700`; um diretório de dados preexistente com permissões para grupo/outros é recusado (`chmod 700 /caminho/dos/dados` após verificar que é o diretório correto). Use um diretório de dados privado fora do checkout, se possível.

A interface usa uma sessão em memória com cookie `HttpOnly` e `SameSite=Strict`. O token da ponte é separado do proprietário. Em Configurações → Consentimento da ponte, o proprietário pode autorizar **independentemente** receber eventos e compartilhar contexto/histórico técnico. Ambos iniciam desligados, expiram em até 8 horas e são revogados ao bloquear a sessão ou reiniciar. Não há integração F9 instalada. Arquivos de credenciais são temporários e removidos no encerramento normal; após encerramento abrupto, arquivos remanescentes são inválidos e podem ser apagados localmente. A reinicialização troca os tokens.

> Este é um servidor HTTP de usuário único, com proteção local de protótipo, não uma solução de produção. Processos com acesso à conta/diretório do usuário podem obter os tokens; não há TLS, autenticação multiusuário, isolamento contra código executado no mesmo processo, limite robusto contra abuso ou revisão de segurança independente. Não publique o servidor nem o coloque atrás de proxy.

## Primeira utilização

1. O habitat decorativo abre sem um personagem de substituição. Em **Configurações → Mídia aprovada do SL-001**, escolha o slot e importe apenas os arquivos originais autorizados. Use `idle_video`/`idle_poster` como base; `happy`, `thinking`, `resting` e `milestone` são opcionais. MP4/WebM e JPG/PNG/WebP, até 50 MiB por arquivo.
2. O player preserva bytes e SHA-256, seleciona mídia por humor, usa fallback para idle, aceita FIT/FILL e reproduz milestone uma vez. A paridade com F8 e a reprodução dos arquivos definitivos **não puderam ser validadas** porque eles não estão disponíveis.
3. Experimente **Brincar**, **Descansar**, **Explorar**, **Aprender**, **Criar** e **Conversar**. O aprendizado e a criatividade usam uma lista local; a conversa responde com textos pré-definidos. O formulário não envia o texto digitado ao servidor; ao fechar o diálogo, a entrada e a conversa visíveis são limpas. Uma operação pendente pode conservar uma cópia em memória até terminar; não é apagamento seguro do navegador.
4. Veja todos os seis atributos em **Como ele está → Ver todos**, a progressão em **Minha jornada** e os registros em **Diário/Memórias**. Registros podem ser apagados individualmente ou em lote. O histórico de XP mantém os itens carregados em atualizações e recargas da mesma aba, quando `sessionStorage` está disponível; a recarga continua abrindo **Meu slime** e não restaura a rolagem.
5. A autonomia vem desligada. Ative-a em Configurações se desejar. É verificada ao consultar o estado, com a página visível em intervalos de 60 segundos e ao voltar; após uma ausência executa no máximo um ciclo atrasado. Não é uma tarefa Android de fundo.

## Testes

```bash
python3 -m unittest discover -s tests -v
# Demonstra evolução com ações locais e dias simulados, em banco temporário:
PYTHONPATH=. python3 tests/evolution_scenario.py
# Cenário HTTP com credenciais fictícias e permissões concedidas/revogadas:
PYTHONPATH=. python3 tests/bridge_scenario.py
```

Os testes usam bancos temporários e não modificam o banco do usuário. Para testes opcionais de interface com Node 22+ e Chrome/Chromium instalado:

```bash
npm ci                    # instala somente dependências de teste, não de execução
CHROME_BIN=/caminho/para/chromium npm run test:browser
CHROME_BIN=/caminho/para/chromium npm run test:evolution
CHROME_BIN=/caminho/para/chromium npm run test:pagination
# Opcional: grava capturas do teste de evolução em diretório escolhido:
CHROME_BIN=/caminho/para/chromium EVIDENCE_DIR=/tmp/evidencias-muse npm run test:evolution
```

`test:browser` inicia um servidor isolado, autentica a sessão, concede e revoga a entrada da ponte, confere layouts desktop/celular e usa `tests/fixtures/solid-color-test.webm`, um vídeo de cores sem personagem, para testar o mecanismo de playback e milestone. Ele força `--autoplay-policy=no-user-gesture-required`; não valida autoplay normal, as mídias aprovadas, F8/F9 ou testes físicos Android.

`test:evolution` não usa mídia nem a ponte. Em bancos descartáveis, verifica as seis ações, os seis atributos, quatro telas, atividades manuais do Diário, histórico, Tab/Enter, foco, barra e atributos ARIA, arredondamento, fórmula configurada, largura móvel e recarga. Exercita conversa curta e elegível, bloqueio, novo login, outra sessão e reinício limpo com o mesmo SQLite, além de verificar marcador de teste nas requisições e no banco. A atualização ao retorno de visibilidade é exercitada por minimização/restauração via Chromium headless; não demonstra troca manual de aba nem garante sincronização instantânea. Também testa as transições de todos os seis estágios, inclusive uma fronteira com mais de 10.000 eventos antigos, e os rótulos de humor e tendência no Diário/Memórias sem alterar os registros persistidos. Para gerar estados avançados, executa ações locais com dias simulados: não é uma passagem de tempo real nem teste em aparelho físico. Respostas são retidas apenas no navegador de teste para verificar corridas e falhas. Evidências e limites: [área evolutiva](reports/AREA_EVOLUTIVA.md), [conversa e convivência](reports/CONVIVENCIA_CONTINUA.md), [jornada e teclado](reports/JORNADA_E_ACESSIBILIDADE.md), [fluxos locais](reports/FLUXOS_LOCAIS.md) e [revisão de XP](reports/EXPERIENCIA_EVOLUTIVA.md).

`test:pagination` usa bancos temporários e verifica páginas sucessivas, falhas recuperáveis, atualização, recarga na mesma aba, novas concessões, mais de 500 itens e os botões de Memórias/Diário. Também retém respostas de páginas antigas durante exclusão, nova atividade e atualização após ação em outra página; verifica que os dados continuam coerentes e a leitura pode ser repetida. Na jornada, verifica foco com Tab/Enter, aviso de status e a árvore de acessibilidade do Chromium, mas não substitui um teste com leitor de tela. Ele não testa Android físico nem mídia do personagem. Detalhes: [revisão final](reports/REVISAO_FINAL.md), [jornada e teclado](reports/JORNADA_E_ACESSIBILIDADE.md) e [paginação local](reports/PAGINACAO.md).

## Dados, privacidade e backup local

Por padrão o SQLite e as mídias importadas ficam em `data/` (ignorado pelo Git). Há migrações transacionais via `PRAGMA user_version`; a versão atual é 2. Ao apagar memórias na interface, o estado, IDs de deduplicação e concessões de XP permanecem. Para um reset integral, pare o servidor e apague o diretório de dados **somente depois de fazer backup**; isso inclui o banco, arquivos `-wal`/`-shm` e mídias importadas. IDs de eventos não devem conter informações pessoais.

Para exportar dados reais, pare o servidor para que banco e mídias correspondam ao mesmo instante e use:

```bash
python3 tools/export_private_data.py --data-dir /caminho/dos/dados --output /caminho/privado/snapshot --server-stopped
cd /caminho/privado/snapshot && sha256sum -c SHA256SUMS
```

O utilitário usa a API `sqlite3.Connection.backup()` para incluir transações já confirmadas no WAL. Não copie apenas o `.sqlite3` enquanto houver um WAL ativo. A cópia deve ser acompanhada do diretório de mídias e armazenada em local autorizado. O ZIP de entrega contém código, documentação, recursos de demonstração e logs de teste, **não** o banco de execução nem mídias privadas importadas. Para um backup integral de dados reais, faça um snapshot consistente do SQLite e inclua também as mídias de `data/media` após autorização; não inclua credenciais.

## Documentação

- [Inspeção e licença do TamAGI](docs/TAMAGI_ANALISE.md)
- [Arquitetura, persistência e privacidade](docs/ARQUITETURA.md)
- [Atributos, XP e evolução](docs/ATRIBUTOS_E_EVOLUCAO.md)
- [Ponte e contratos Muse](docs/CONTRATO_MUSE.md)
- [Recursos visuais e player](docs/RECURSOS_VISUAIS.md)
- [Entrega web: telas, evolução e testes](reports/ENTREGA_WEB.md)
- [Revisão final dos quatro fluxos](reports/REVISAO_FINAL.md)
- [Fluxo da área evolutiva e fronteira de eventos](reports/AREA_EVOLUTIVA.md)
- [Conversa e convivência contínua](reports/CONVIVENCIA_CONTINUA.md)
- [Fluxos locais e sincronização](reports/FLUXOS_LOCAIS.md)
- [Paginação e recarga](reports/PAGINACAO.md)
- [Jornada e uso por teclado](reports/JORNADA_E_ACESSIBILIDADE.md)
- [Resultados e limitações](reports/RESULTADOS.md)
- [Checkpoint](docs/CHECKPOINT.md)
