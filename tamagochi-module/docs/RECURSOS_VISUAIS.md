# Recursos visuais e player

## SL-001 e F8

Os vídeos, posters, player e especificação F8 aprovados não foram encontrados no checkout nem em qualquer pasta acessível nesta sessão. Por essa razão, nenhum slime substituto foi desenhado ou gerado, e nenhum vídeo/poster original foi modificado. O habitat exibe um aviso e um botão de importação até que um recurso real seja fornecido. A aprovação do personagem final continua pendente.

O adaptador HTML5 atual implementa slots `idle`, `happy`, `thinking`, `resting` e `milestone` para vídeo/poster, fallback de estado para idle, reprodução silenciada em loop, `playsinline`, FIT/FILL e milestone único quando um evento correspondente é recebido. Importações são verificadas por assinatura de formato e armazenadas **byte a byte** sob SHA-256; sem transcodificação. O navegador pode não suportar um codec, transparência ou autoplay específico; nesse caso o poster disponível é usado. A semântica exata das transições, estados, posters e milestones F8 deve ser comparada com os originais antes de alegar compatibilidade.

## Proveniência

- `web/assets/habitat.png`: arte ambiental gerada para este protótipo com ferramenta de imagem; não representa nem altera o SL-001 e não veio do TamAGI. Fundo e decorações são camadas independentes do player.
- `tests/fixtures/solid-color-test.webm`: fixture gerada localmente por canvas/MediaRecorder com quadros de cores sólidas, sem personagem; usada exclusivamente para teste técnico. Não é um asset de produto aprovado.
- Ícones e CSS: implementação própria deste protótipo. Nenhum asset do TamAGI foi copiado.

O usuário precisa fornecer os originais aprovados e, se houver, seus hashes e o contrato real F8. Após importá-los, conferir os hashes apresentados em Configurações e executar os testes reais de todos os estados e da milestone. O vídeo final pode cobrir o fundo conforme suas dimensões/transparência; isso depende do material aprovado.
