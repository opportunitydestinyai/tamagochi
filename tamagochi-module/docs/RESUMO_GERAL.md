# Resumo geral do trabalho — Módulo Tamagotchi Evolutivo

**Produto:** Muse AI / Tamagotchi AI  
**Módulo:** Tamagotchi Evolution & Companion  
**Versão do protótipo:** 0.1.0  
**Personagem previsto:** SL-001  
**Referência do resumo:** 28/10/2026

> Atualizações da mesma data: a barra de XP separa progresso do nível e XP acumulado; a interface impede que leituras antigas da mesma aba sobrescrevam ações concluídas e a paginação de XP preserva os itens carregados na recarga da mesma aba, quando o armazenamento está disponível. A revisão posterior também reparou perdas de foco no atalho, na paginação da jornada, nas ações principais e no envio da conversa; não houve teste com leitor de tela. Evidências e limites: [`reports/EXPERIENCIA_EVOLUTIVA.md`](../reports/EXPERIENCIA_EVOLUTIVA.md), [`reports/FLUXOS_LOCAIS.md`](../reports/FLUXOS_LOCAIS.md), [`reports/PAGINACAO.md`](../reports/PAGINACAO.md) e [`reports/JORNADA_E_ACESSIBILIDADE.md`](../reports/JORNADA_E_ACESSIBILIDADE.md). Mídias, F8/F9 e Android físico não foram validados.
>
> A inspeção de conversa e convivência acrescentou testes de logout/login, sessão separada e reinício limpo do processo com o mesmo SQLite, além de comportamento do humor com relógio simulado. Não reproduziu divergência que justificasse alterar o produto. Foram 80 testes Python e três suítes de navegador; sincronização instantânea entre abas não é garantida. Detalhes: [`reports/CONVIVENCIA_CONTINUA.md`](../reports/CONVIVENCIA_CONTINUA.md).
>
> Na revisão posterior do fluxo web evolutivo, passou-se por todas as telas, seis ações, atividades manuais e cinco mudanças de estágio com dias simulados. Uma regressão em que histórico com mais de 10.000 eventos reapresentava avisos antigos foi reproduzida e corrigida sem mudar regras ou mídia. Passaram 82 testes Python e as três suítes de navegador; retorno de visibilidade foi exercitado por minimização/restauração headless, não por troca física de aba. Detalhes: [`reports/AREA_EVOLUTIVA.md`](../reports/AREA_EVOLUTIVA.md).
>
> A revisão final corrigiu respostas antigas de paginação de Memórias/Diário e a contagem da API de Memórias em leituras concorrentes. Passaram 83 testes Python, `test:pagination` e `test:browser`; nessa revisão a suíte de evolução anterior não foi repetida. Detalhes: [`reports/REVISAO_FINAL.md`](../reports/REVISAO_FINAL.md).
>
> Em 29/10, uma revisão de entrega corrigiu a apresentação dos códigos de humor e tendência no Diário/Memórias, sem migrar dados. As três suítes de navegador passaram após a mudança, inclusive a de evolução com dias simulados; os 83 testes Python haviam passado antes da alteração exclusiva de JavaScript. Capturas e limites: [`reports/ENTREGA_WEB.md`](../reports/ENTREGA_WEB.md). Naquela revisão, não houve APK ou publicação no GitHub.

## 1. Objetivo e situação atual

Foi criado um **protótipo independente** de convivência e evolução para ser avaliado e, futuramente, integrado ao Muse Android. Ele reúne estado persistente, atributos, interações, XP, níveis, evolução, personalidade, diário, atividades locais, interface responsiva e contratos de eventos para o Muse.

O protótipo é uma aplicação **web com servidor Python e SQLite**. Não é um APK, não implementa o agente Muse inteiro e não está integrado à F9. A base deste repositório continha apenas um README: **não havia código F1–F9 para inspecionar ou alterar**. Assim, nenhum arquivo dessas fases foi modificado neste checkout, mas isso não comprova o estado de cópias externas do aplicativo.

### Limitações e pendências separadas

O backup remoto é uma pendência separada e não bloqueia a revisão do protótipo web. A integração com Muse Android é futura.

1. Os **vídeos e posters aprovados do SL-001**, a especificação e o player F8 não estavam disponíveis. O espaço do personagem informa essa ausência; não foi criado outro slime para substituí-lo.
2. A integração com a **F9 real** e os testes em um **dispositivo Android físico** ainda não foram realizados.
3. Na última verificação, o Google Drive estava conectado, mas a pasta autorizada **`Muse-REA` não foi localizada**. O backup solicitado não foi enviado nem verificado. É necessário fornecer o link da pasta ou acesso à conta correta.

## 2. Análise da referência TamAGI

Foi inspecionado o repositório [TamAGI](https://github.com/manikmakki/TamAGI), no commit `b3bb5b1e0ee0808e5e928d4ab3d563af42e0fdd6`, incluindo documentação, motor de personalidade, memória, autonomia, API, interface, dependências, licença e presença de testes.

Principais constatações:

- O TamAGI calcula seu nível como `1 + experience // 50` e usa intervalo de 250 XP entre índices de estágio. Essas fórmulas **não são** as adotadas neste módulo.
- Seu código inspecionado usa vitalidade e curiosidade, com humor derivado da vitalidade para seleção de pose. A personalidade é persistida em JSON; a memória usa ChromaDB ou alternativas descritas no projeto.
- O README ainda descreve um antigo Dream Engine e rotas `/api/dreams/*`, mas o código atual inspecionado inicializa o **WorldThread**, descrito como substituto dos mecanismos anteriores. Essas descrições foram diferenciadas no relatório.
- Não foi encontrada uma suíte automatizada na árvore do snapshot inspecionado; isso não prova que o projeto não seja testado por outros meios.
- O repositório declara **AGPL-3.0**. Nenhum código, componente, sprite ou asset dele foi incorporado. As regras e a implementação deste protótipo são próprias; qualquer reutilização direta futura precisa de avaliação das obrigações de licença.

Detalhes: [análise técnica e licenciamento](TAMAGI_ANALISE.md).

## 3. Arquitetura implementada

```text
Interface web responsiva
        │ HTTP/JSON de mesma origem
        ▼
Servidor Python independente
        │
        ├── PetEngine e regras determinísticas
        ├── Scheduler e atividades locais
        ├── MusePetBridge e eventos normalizados
        └── SQLite: estado, memórias, XP e eventos
```

O código está em [`tamagochi-module/`](../). Os principais componentes são:

| Arquivo ou diretório | Função |
|---|---|
| `pet/model.py` | Atributos, configuração e motores de humor, personalidade, XP, evolução e atividades. |
| `pet/service.py` | `PetEngine`, regras transacionais, ações, autonomia e eventos. |
| `pet/repository.py` | Persistência SQLite e migrações versionadas. |
| `pet/autonomy.py` | Fachada `AutonomyScheduler`. |
| `pet/bridge.py` | Contratos normalizados para futura integração Muse. |
| `pet/media.py` | Importação controlada de vídeos e posters. |
| `app.py` | Servidor HTTP do protótipo. |
| `web/` | Interface, estilos, player adaptador e ambiente decorativo. |
| `tests/` e `tools/` | Testes, fixtures, validação no navegador, exportação e empacotamento. |

Não há dependência obrigatória de LLM, ChromaDB, contas externas ou API paga. Desde a revisão de segurança, são gerados tokens locais temporários distintos para proprietário e ponte. O servidor aceita apenas localhost e não deve ser publicado como serviço de produção.

## 4. Motor, estado e persistência

O estado inicial configurado para o SL-001 é:

| Indicador | Valor inicial |
|---|---:|
| Felicidade | 75 |
| Energia | 80 |
| Curiosidade | 50 |
| Conhecimento | 10 |
| Vínculo | 20 |
| Confiança | 50 |
| XP / nível | 0 XP / nível 1 |
| Humor / atividade | `CALM` / `IDLE` |

Os atributos são limitados ao intervalo de 0 a 100. O humor é derivado de atributos, atividade e sinais recentes, sem sorteio a cada atualização da tela. Os traços são tendências de comportamento e não mudam a identidade do companheiro.

O estado, a configuração, as memórias, o histórico de XP e os eventos ficam em SQLite. O esquema usa migrações versionadas, atualmente na **versão 2**. Cada comando grava alterações, identificadores de eventos, XP, memórias e eventos de saída na mesma transação; uma falha deve reverter a operação inteira.

O tempo decorrido é tratado de maneira limitada: por padrão, há recuperação leve de energia de 0,5 ponto por hora, considerando no máximo 24 horas por reconciliação. Uma reversão de relógio não permite repetir a recuperação. Não há morte do pet nem perda severa de felicidade ou vínculo por ausência.

## 5. Interações e experiência

Foram implementadas ações com consequências reais no estado:

- **Brincar:** melhora felicidade e vínculo, consumindo energia.
- **Descansar:** recupera energia.
- **Explorar:** usa uma lista local de temas e registra uma descoberta.
- **Aprender:** apresenta uma informação de uma lista local e aumenta conhecimento.
- **Criar:** apresenta uma ideia escolhida de uma lista local.
- **Conversar:** registra a interação e usa respostas locais pré-definidas; não simula um agente geral.
- Consultar diário, evolução, atributos e personalização também possui navegação funcional.

O formulário não envia o texto digitado ao servidor; ao fechar o diálogo, a entrada e a conversa visíveis são limpas. Uma operação pendente pode conservar temporariamente uma cópia em memória do navegador. O indicador de conversa significativa é uma aproximação por comprimento — 30 unidades UTF-16 de JavaScript por padrão —, não uma análise semântica.

### XP e níveis

O nível é derivado do XP acumulado. A fórmula padrão para chegar ao nível `n` é:

```text
XP(n) = arredondar para inteiro: 100 × (n − 1)^1,5
```

Os ganhos iniciais incluem primeira interação do dia, conversa significativa, tarefa ou meta confirmada, nova habilidade, aprendizado, criação e marco confirmado. Há deduplicação por `eventId`, proteção adicional por identificador lógico de tarefa/meta/habilidade/marco, limites por tipo de evento e teto padrão de **120 XP por dia**. Eventos repetidos ou não confirmados não devem conceder XP novamente.

Os valores, efeitos, limites, faixas e outras regras principais estão em `config.example.json` e podem ser configurados e persistidos. A fórmula e as faixas ficam bloqueadas após o primeiro ganho de XP para evitar perda arbitrária de níveis.

## 6. Evolução e personalização

A evolução é funcional, comportamental e ambiental: **não transforma a espécie nem altera os vídeos do personagem**. Os estágios padrão e suas recompensas implementadas são:

| Nível | Estágio | Recompensa no protótipo |
|---:|---|---|
| 1–4 | Despertar | Habitat básico e interações. |
| 5–9 | Descoberta | Moldura de descoberta. |
| 10–19 | Aprendizado | Emblema de estágio. |
| 20–34 | Companheiro | Opção de decoração halo. |
| 35–49 | Explorador | Opção de ambiente Aurora. |
| 50+ | Evoluído | Constelação e emblema. |

As atividades básicas já estão disponíveis desde o início; os limites e nomes de estágio são propostas de balanceamento. Há também tendências independentes de nível — explorador, criador, pesquisador, organizador e companheiro — calculadas a partir das atividades. As tendências não bloqueiam funções do futuro agente.

Evoluções e recompensas são registradas, persistidas, emitidas como eventos e exibidas na interface. O milestone visual depende de um vídeo aprovado ser importado.

## 7. Autonomia, diário e memória

A autonomia é **local e desativada por padrão**. As quatro atividades implementadas são:

1. **Sonhar:** resume registros do próprio pet, sem inventar fatos sobre o usuário.
2. **Explorar:** escolhe um tema de uma lista local, sem pesquisa na internet.
3. **Experimentar:** apresenta uma ideia pré-definida, sem LLM.
4. **Diário:** registra um resumo local do estado e das atividades.

O agendamento permite ativar/desativar, definir intervalo e horário de descanso, respeitar custos de energia e consultar histórico. A verificação ocorre ao consultar o estado e periodicamente com a página visível; após uma ausência, executa no máximo um ciclo atrasado. Não há serviço Android rodando em segundo plano.

Memórias podem ser consultadas e apagadas. Ao apagar registros pela interface, os identificadores técnicos e o histórico de XP permanecem para impedir duplicações; um reset integral exige remover os dados locais com o servidor parado. Não se deve colocar segredos em IDs ou payloads da ponte.

## 8. Interface e recursos visuais

A interface possui habitat, status e atributos, ações, jornada/evolução, diário, memórias, configurações e personalização. Ela foi avaliada em tamanhos de tela de desktop e celular.

O fundo do habitat é uma **arte ambiental decorativa** gerada para este projeto, sem personagem. Vídeos e posters originais não foram recriados, redesenhados ou modificados.

Foi preparado um player HTML5 adaptador com slots para `idle`, `happy`, `thinking`, `resting` e `milestone`, fallback para `idle`, reprodução silenciosa, FIT/FILL e milestone não repetitivo. As mídias fornecidas pelo usuário são importadas preservando os bytes e o SHA-256. Como os originais e o player F8 não estavam disponíveis, **a compatibilidade exata com F8 e o comportamento das mídias reais permanecem pendentes**.

Na revisão posterior dos testes, foi encontrado e corrigido um problema no qual notificações empilhadas podiam bloquear cliques no celular. As notificações agora não interceptam cliques e são limitadas a três; o teste de navegador verifica essa correção.

## 9. Ponte para o Muse

`MusePetBridge` recebe eventos normalizados, sem importar classes internas F1–F9. As fixtures cobrem os 12 tipos de entrada propostos, incluindo conversa, início/conclusão/falha de tarefa, metas, aprovações, atualização de memória, ferramenta e milestone.

Os eventos de saída incluem mudança de humor, aumento de nível, evolução, início/conclusão de atividade, vínculo e recompensa. Eles são persistidos e consultáveis por cursor. O contexto exportado ao futuro agente contém apenas dados do pet, como humor, traços dominantes, vínculo, nível e atividade.

A ponte exige token próprio e consentimento independente para receber eventos e compartilhar contexto/histórico; os dois escopos começam desativados, expiram e podem ser revogados. Ela foi testada **com o contrato proposto e fixtures**, não com a F9 real. Antes de qualquer integração será necessário conferir esquemas, identificadores, transporte, identidade, consentimento e compatibilidade com o aplicativo existente. Detalhes: [contrato Muse](CONTRATO_MUSE.md).

## 10. Testes realizados

A revisão posterior de segurança registrou localmente 19 testes específicos e 74 testes Python no total, além do teste de navegador com sessão e consentimento. A medição e suas limitações estão em `reports/seguranca-ponte.log`. Na revisão de paginação, passaram 78 testes Python e os testes geral, de evolução e de paginação em navegador; os estados avançados usam dias simulados. O diagnóstico que havia falhado na revisão de fluxos passou após a correção. Detalhes em `reports/PAGINACAO.md`. Isso é evidência textual local, não verificação independente.

Na revisão anterior à proteção de acesso (resultados históricos, não cobertura da versão atual):

- **55 testes Python passaram**, sem casos ignorados, em bancos temporários.
- O teste de navegador passou para tamanhos de desktop e celular, cobrindo ações, atributos, privacidade da conversa, personalização, autonomia, exclusão de memórias, vídeo neutro e milestone.
- A cobertura medida foi de **90% das linhas Python** dos módulos selecionados. A medida não inclui JavaScript nem cobertura de ramificações e não garante ausência de defeitos.
- A revisão acrescentou testes diretos para `AutonomyScheduler` e um teste de regressão para os cliques obstruídos por notificações.
- Foram exercitados deduplicação concorrente, falha de armazenamento, recuperação após interrupção, limites de atributos e XP, migração de banco, ausência longa, reversão de relógio, exportação privada e integridade do pacote.

**Ainda não testado:** os vídeos/posters definitivos do SL-001, a equivalência com F8, a integração real com F9 e um dispositivo Android físico. O vídeo usado no teste é apenas um padrão de cores sem personagem.

Relatórios e logs históricos: [resultados](../reports/RESULTADOS.md), [log Python](../reports/testes-unitarios.log), [log de navegador](../reports/testes-navegador.log) e [cobertura Python](../reports/cobertura-python.log). Consulte também `reports/seguranca-ponte.log` para a revisão de autenticação e consentimento. A evidência é local e não foi verificada independentemente pelo usuário.

## 11. Arquivos entregues e backup

- [Projeto e instruções completas](../README.md).
- [Análise do TamAGI](TAMAGI_ANALISE.md), [arquitetura](ARQUITETURA.md), [regras de atributos e evolução](ATRIBUTOS_E_EVOLUCAO.md) e [contrato Muse](CONTRATO_MUSE.md).
- [Manifesto de arquivos](MANIFESTO.md) e [SHA-256 dos arquivos do projeto](../SHA256SUMS).
- [ZIP local do projeto](../../Modulo_Tamagotchi_Evolutivo_T1.zip) e [SHA-256 do ZIP](../../Modulo_Tamagotchi_Evolutivo_T1.zip.sha256).
- [Checkpoint de continuidade](CHECKPOINT.md).

O ZIP contém código, documentação, testes, logs e recursos de demonstração. Ele **não inclui automaticamente dados de execução nem mídias privadas importadas**. Um backup de dados reais deve incluir um snapshot consistente do SQLite e as mídias autorizadas, conforme as instruções do projeto.

**Google Drive:** na última busca, o conector estava ativo, mas `Muse-REA` não foi encontrada. Nenhuma pasta foi criada e nenhum upload foi verificado. O ZIP local **não equivale** ao backup obrigatório no Drive.

## 12. Como executar e próximos passos

### Execução local

```bash
cd tamagochi-module
python3 app.py
```

Abrir `http://127.0.0.1:8765` no navegador da mesma máquina e desbloquear com o conteúdo do arquivo privado `owner.token` cujo caminho aparece no terminal. Não compartilhe a credencial. O servidor deve permanecer ativo e não suporta preview remoto.

### Executar a suíte Python

```bash
cd tamagochi-module
python3 -m unittest discover -s tests -v
```

Para o teste opcional de navegador, consulte o README do módulo; ele requer Node.js, `puppeteer-core` e um Chrome/Chromium local.

### Próximos passos prioritários

1. Receber o **link da pasta `Muse-REA`** ou acesso à conta correta; criar a subpasta solicitada, enviar o pacote e, se aplicável, um snapshot dos dados e das mídias autorizadas; verificar uploads e fornecer links diretos.
2. Receber os **vídeos, posters e especificação F8 aprovados**; importar sem alterar, conferir hashes e validar estados, FIT/FILL e milestones reais.
3. Inspecionar a **F9 real** quando disponibilizada e adaptar a ponte aos contratos efetivos, sem alterar F1–F9 nesta fase.
4. Planejar a implementação Android apropriada e executar testes físicos de interface, acessibilidade, consumo, armazenamento e recuperação.
