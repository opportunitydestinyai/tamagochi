# Atributos, ações, XP e evolução

Os valores a seguir são hipóteses próprias do módulo, configuráveis e persistidas; não são valores comprovados do Muse nem fórmulas copiadas do TamAGI.

## Estado inicial

| Atributo | Inicial | Limite | Significado |
|---|---:|---:|---|
| Felicidade | 75 | 0–100 | Bem-estar |
| Energia | 80 | 0–100 | Disposição |
| Curiosidade | 50 | 0–100 | Tendência a explorar |
| Conhecimento | 10 | 0–100 | Aprendizado local |
| Vínculo | 20 | 0–100 | Convivência positiva |
| Confiança | 50 | 0–100 | Segurança nas interações |
| XP | 0 | inteiro ≥0 | Experiência acumulada |
| Nível | 1 | derivado de XP | Progressão geral |
| Humor / atividade | CALM / IDLE | derivados / enum | Expressão e atividade |

Em `config.example.json` e Configurações → JSON: atributos e traços iniciais para banco novo, efeitos das ações/atividades, custos, ganhos, limites diários, fórmula, faixas, limiares de humor, incremento de traço, duração do sinal recente, mínimo aproximado da conversa, recuperação passiva e scheduler. Alterar atributos iniciais em um banco já criado não modifica o estado atual. Para um novo estado inicial, utilize `--config` com diretório de dados novo. A fórmula e os limites de estágio são bloqueados após o primeiro XP para evitar perda arbitrária de níveis.

## Efeitos padrão por ação concluída

| Ação | Efeito | Resultado real |
|---|---|---|
| Brincar | felicidade +8, energia −10, vínculo +3, confiança +1 | Registro de atividade |
| Descansar | energia +20 | Recuperação imediata |
| Explorar | curiosidade +5, energia −8, felicidade +2 | Tema de uma lista local |
| Aprender | conhecimento +4, energia −7, curiosidade +2 | Pequena informação de uma lista local |
| Criar | felicidade +3, energia −7, curiosidade +2 | Ideia de uma lista local |
| Conversar | felicidade +2, vínculo +2, confiança +1 | Resposta local pré-definida; texto não é guardado |

Todos os atributos são limitados a 0–100 e ações com energia insuficiente não são confirmadas. A recuperação passiva padrão é 0,5 energia/hora, aplicada a no máximo 24 horas transcorridas, sem punição por ausência. Os traços sobem 2 pontos por atividade associada; as duas maiores tendências são exibidas. Os traços não formam identidades diferentes.

## Humor

Determinístico. `RESTING` se a atividade estiver descansando; energia ≤25 causa `TIRED`; sinais recentes válidos (`RESTING`, `PROUD`, `FOCUSED`, `EXCITED`, `CURIOUS`) duram 20 minutos por padrão; senão felicidade ≥90 e energia ≥60 = `HAPPY`, curiosidade ≥75 = `CURIOUS`, felicidade <30 = `BORED`, demais casos = `CALM`. Limiares e duração são configuráveis. Não há sorteio por renderização.

## XP

XP acumulado necessário para alcançar nível `n`: `arredonda_metade_para_cima(100 × (n−1)^1,5)`. Níveis 1 a 6 começam em 0, 100, 283, 520, 800 e 1118 XP. O nível é derivado por busca dos limiares, não mantido como contador independente.

Na tela principal, **XP neste nível** e a barra usam `intoLevel / neededInLevel`; a linha separada mostra XP acumulado e o limiar acumulado seguinte. Por exemplo, com 150 XP totais, o nível 2 começa em 100 e o próximo em 283: aparecem **50 / 183 XP**, barra de **27,3%**, total 150 e faltam 133. Ao atingir exatamente 100 XP, a barra recomeça em 0/183; não há perda de XP. Para evitar um 100% prematuro por arredondamento, o percentual exibido é no máximo 99,9% enquanto faltar XP para o nível seguinte. Isso não altera os limiares nem o XP. Os valores vêm de `state.progress`, calculado com a configuração persistida. A barra expõe o mesmo progresso em atributos ARIA; isso não substitui testes com leitores de tela.

| Conclusão | XP | Limite padrão/dia local |
|---|---:|---:|
| Primeira interação | 5 | 1 |
| Conversa considerada significativa | 2 | 3 |
| Tarefa confirmada | 15 | 5 |
| Meta confirmada | 30 | 3 |
| Nova habilidade confirmada | 10 | 3 |
| Aprender | 8 | 5 |
| Criar/experimento | 8 | 5 |
| Marco confirmado | 25 | 3 |

Teto total de **120 XP/dia**, com concessão parcial quando necessário. Dia é determinado pelo horário de recebimento no fuso configurado, não pelo timestamp não confiável do produtor. Na UI sem LLM, “significativa” é uma aproximação explícita: pelo menos 30 caracteres por padrão, avaliados no navegador; não significa compreensão semântica. O produtor Muse deve fornecer o booleano conscientemente. IDs são deduplicados, conclusão deve ser confirmada e o histórico de concessões é paginado. Sem perda arbitrária de XP.

## Estágios e tendências

| Nível padrão | Estágio | Recompensa implementada |
|---:|---|---|
| 1 | Despertar | Habitat básico e interações iniciais |
| 5 | Descoberta | Moldura de descoberta no habitat |
| 10 | Aprendizado | Emblema de estágio |
| 20 | Companheiro | Opção de decoração halo |
| 35 | Explorador | Opção de ambiente Aurora |
| 50 | Evoluído | Decoração constelação e emblema |

As recompensas são camadas separadas e não transformam o SL-001. A especialização é independente do nível: explorador, criador, pesquisador, organizador ou companheiro, conforme contagens de ações; por padrão requer 3 atividades, preserva o líder em empate e nunca bloqueia funções do agente. As contagens e eventos são persistidos. Ao cruzar uma faixa: outbox, memória, recompensa, atualização de UI e pedido de milestone são registrados; o vídeo só toca se a mídia aprovada tiver sido importada.
