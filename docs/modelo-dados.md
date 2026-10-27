# Modelo de dados

A seção 10 da especificação pedia validação antes da primeira migration. Este documento descreve a proposta final, já ajustada pelas decisões de `docs/decisoes.md`. A migration `0001` só chega à produção depois que a PR da Fase 1 for mesclada, e é esse o ponto de validação.

Convenções:
- Todas as tabelas de domínio têm `familia_id`, porque o sistema é multi-tenant (decisão 8).
- Os instantes são gravados como `timestamptz`, em UTC. As regras baseadas em "dia" usam `America/Sao_Paulo`.
- Valores ficam em `NUMERIC(10,2)`. Pontos usam a mesma coluna, e uma constraint garante que sejam inteiros.
- Nenhum registro com histórico é excluído fisicamente. Para tirar algo de uso, o campo `ativo` é desligado.
- Os tipos e status são `VARCHAR` com `CHECK`, e não `ENUM` nativo, porque assim é mais simples evoluir por migration.

## Fase 1 (migration `0001`)

| Tabela | Campos principais | Observações |
|--------|-------------------|-------------|
| `familia` | id, nome, pin_parental_hash, criado_em | Há um PIN por família (decisão P4), guardado com hash Argon2id. |
| `configuracao_familia` | familia_id (PK), permite_saldo_negativo, advertencias_antes_penalidade, penalidade_max_diaria_brl, penalidade_max_diaria_pontos, som_ativo | As decisões da seção 13 aparecem aqui como parâmetros. |
| `responsavel` | id, familia_id, nome, email (único global), senha_hash, ativo, ultimo_login_em | O hash da senha é Argon2id. |
| `crianca` | id, familia_id, nome, foto, cor_avatar, data_nascimento, ativo | Tem `UNIQUE (id, familia_id)`, que serve de alvo para a FK composta do ledger. |
| `lancamento` | id, familia_id, crianca_id, tipo, unidade (`BRL`/`PONTOS`), valor (com sinal), observacao, autor_responsavel_id, estorno_de_id (UNIQUE), lote_id, criado_em | Livro-razão imutável. Detalhes abaixo. |
| `auditoria` | id, familia_id, autor_responsavel_id, acao, entidade, entidade_id, antes (JSON), depois (JSON), em | Os hashes de senha e de PIN nunca entram aqui. |
| `tentativa_acesso` | id, chave, em | Guarda as tentativas para o rate limit de login e de PIN, e vale para todos os workers. |

### Garantias do ledger (`lancamento`)

| Regra | Onde é garantida |
|-------|------------------|
| Sem UPDATE e sem DELETE | Trigger no banco e listener do SQLAlchemy |
| Um estorno por lançamento | `UNIQUE (estorno_de_id)` e verificação no service, com a criança travada |
| Não existe estorno de estorno | Service |
| `ESTORNO` sempre referencia o lançamento original | `CHECK` |
| `AJUSTE_MANUAL` exige motivo | `CHECK` e service |
| Créditos são positivos e débitos negativos | `CHECK` e service |
| `PAGAMENTO` só em R$ e limitado ao saldo | `CHECK` e service (decisão P2) |
| Pontos são inteiros | `CHECK` e service |
| A criança pertence à família do lançamento | FK composta `(crianca_id, familia_id)` |
| Piso zero (decisão 4) | Service, com `SELECT … FOR UPDATE` na criança |
| Saldo = soma dos lançamentos | Não há saldo materializado. Um teste de propriedade (Hypothesis) verifica a regra. |

A trava na linha da criança serializa as operações concorrentes sobre a mesma criança, como um duplo toque ou dois responsáveis agindo ao mesmo tempo. O teste `test_debitos_concorrentes_respeitam_piso_zero` falha quando essa trava é removida.

O ledger aceita DELETE em uma única situação: a futura exclusão completa de uma família (LGPD). Nesse caso a transação precisará executar `SET LOCAL mesada.exclusao_familia = 'on'`.

## Próximas fases (migrations futuras, sujeitas a ajuste)

| Fase | Tabelas | Notas |
|------|---------|-------|
| 2 | `tarefa` (valor_brl, valor_pontos — P1; recorrência; janela; limite_por_periodo), `tarefa_crianca`, `ocorrencia_tarefa` | Não haverá `exige_aprovacao`, porque toda tarefa é aprovada (decisão 2). A ocorrência terá `UNIQUE (tarefa_id, crianca_id, data_referencia, sequencial)` para garantir idempotência. O ledger ganhará a coluna `ocorrencia_tarefa_id`. |
| 3 | `regra_proibicao` (valor_brl, valor_pontos, gravidade), `regra_crianca`, `ocorrencia_penalidade` (com `lote_id` para registro coletivo — decisão 7) | Não haverá `advertencias_antes` por regra, porque o padrão é global (decisão 5). O ledger ganhará `ocorrencia_penalidade_id`. |
| 4 | `premio` (custo_brl, custo_pontos), `resgate`, `objetivo` | Não haverá `fechamento_periodo` (decisão 9). O pagamento é um lançamento avulso (P2). O ledger ganhará `resgate_id`. |
