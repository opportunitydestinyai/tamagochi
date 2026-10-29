# Muse Companion · SL-001

Protótipo independente de convivência e evolução para o Muse. O projeto nesta branch **não contém nem modifica o Muse Android F1–F9**. A implementação não é o agente Muse e não requer LLM, ChromaDB, contas externas ou APIs pagas. Credenciais locais temporárias são geradas para proteger o acesso.

## Executar

Requer Python 3.11+ com base de fusos IANA (`zoneinfo`). Não há dependências de execução além da biblioteca padrão.

```bash
cd tamagochi-module
python3 app.py
```

Abra `http://127.0.0.1:8765` no navegador da **mesma máquina**. O terminal informa o caminho do arquivo privado `owner.token`; use-o na tela de desbloqueio, sem compartilhar o conteúdo. A ponte tem outra credencial e inicia sem consentimento para receber ou compartilhar. Ambas as credenciais mudam a cada execução. Veja as instruções de [segurança e consentimento](tamagochi-module/docs/CONTRATO_MUSE.md#autenticação-e-consentimento-do-protótipo).

O servidor aceita somente bind local; `--host 0.0.0.0`, proxies e preview remoto estão bloqueados. A proteção é para um protótipo de usuário único, não para produção. Não exponha o servidor nem inclua credenciais em backups ou mensagens.

## Situação importante

- **Os vídeos/posters aprovados do SL-001 e a especificação/player F8 não foram fornecidos neste checkout.** A interface identifica a ausência e permite importar os arquivos originais sem alterá-los; não foi criado outro personagem. A imagem de fundo é apenas um ambiente decorativo novo.
- **O Google Drive está conectado, mas a pasta autorizada `Muse-REA` não foi localizada.** O backup solicitado não foi enviado nem verificado; é uma pendência separada, não bloqueante para a revisão web. O ZIP local é um pacote de código e recursos disponíveis, não um backup confirmado no Drive.
- F8/F9 reais, autoplay sob política normal e execução em Android físico permanecem sem validação. Este é um **protótipo web + Python/SQLite**, não um APK nem uma integração concluída com Android.

O [ZIP do projeto](Modulo_Tamagotchi_Evolutivo_T1.zip) e seu [SHA-256](Modulo_Tamagotchi_Evolutivo_T1.zip.sha256) contêm código, documentação, testes e evidências locais, sem banco real, credenciais ou dependências instaladas. A verificação local não demonstra acesso independente nem backup no Drive. Os registros de validação na raiz identificam versões anteriores pelo hash e permanecem históricos.

Consulte a [entrega web com telas e testes](tamagochi-module/reports/ENTREGA_WEB.md), o [resumo geral do trabalho](tamagochi-module/docs/RESUMO_GERAL.md), as [instruções detalhadas](tamagochi-module/README.md), a [análise do TamAGI](tamagochi-module/docs/TAMAGI_ANALISE.md), o [contrato Muse](tamagochi-module/docs/CONTRATO_MUSE.md), a [revisão final da área web](tamagochi-module/reports/REVISAO_FINAL.md), [fluxo da área evolutiva](tamagochi-module/reports/AREA_EVOLUTIVA.md), [conversa e convivência contínua](tamagochi-module/reports/CONVIVENCIA_CONTINUA.md), [fluxos locais e sincronização](tamagochi-module/reports/FLUXOS_LOCAIS.md), [paginação e recarga](tamagochi-module/reports/PAGINACAO.md), [jornada e uso por teclado](tamagochi-module/reports/JORNADA_E_ACESSIBILIDADE.md), [revisão de XP](tamagochi-module/reports/EXPERIENCIA_EVOLUTIVA.md), [resultados](tamagochi-module/reports/RESULTADOS.md) e [checkpoint](tamagochi-module/docs/CHECKPOINT.md).
