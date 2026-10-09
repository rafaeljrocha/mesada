# Decisões de produto — Sistema de Mesada por Mérito

Registro da Fase 0. Respostas do responsável em 2026-10-09.
Itens marcados **PROVISÓRIO** ainda não foram decididos e serão implementados como parâmetro configurável com o padrão indicado.

## Decisões da seção 13

| # | Decisão | Escolha | Consequência técnica |
|---|---------|---------|----------------------|
| A | Localização do código | **Repositório novo e separado** | Nada deste sistema entra em `rafaeljrocha/gruporc`. |
| 1 | Unidade da recompensa | **(d) R$ e pontos independentes** | Dois saldos por criança (BRL e PONTOS), sem conversão entre eles. Cada lançamento tem uma única unidade. Tarefas, regras e prêmios informam valor em R$, em pontos ou em ambos (ver P1). |
| 2 | Aprovação de tarefas | **(a) Sempre exige aprovação** | "Fiz!" leva a `MARCADA_PELA_CRIANCA`; o crédito só é lançado em `APROVADA`. O campo `exige_aprovacao` por tarefa **não** será criado. |
| 3 | Mesada-base fixa | **(a) Não existe, 100% mérito** | O tipo `CREDITO_MESADA_BASE` fica previsto no enum do ledger, mas sem rotina automática. |
| 4 | Saldo negativo | **(b) Piso zero** | O débito de penalidade é limitado ao saldo disponível **na unidade da penalidade**. Parâmetro `permite_saldo_negativo` mantido (padrão `false`), conforme exigido pela seção 6.3. |
| 5 | Advertência antes da penalidade | **(b) Padrão global** | Parâmetro de família `advertencias_antes_penalidade`; a regra não tem campo próprio. Contagem por dia (America/Sao_Paulo). |
| 6 | Identificação da criança | **(a) Só tocar na foto** | Sem PIN infantil. A aprovação obrigatória (item 2) compensa o risco de um irmão marcar pelo outro. |
| 7 | Ocorrências coletivas | **Sim** | Registro coletivo como atalho na UI; internamente, uma `ocorrencia_penalidade` e um `lancamento` **por criança**, com `lote_id` comum. Anulação individual ou do lote inteiro. |
| 8 | Arquitetura | **(b) Multi-tenant desde a 1ª migration** | `familia_id` em todas as tabelas de domínio; isolamento por família verificado por teste. |
| 9 | Fechamento | **Sem fechamento (saldo contínuo)** | A tabela `fechamento_periodo` não será criada. Pagamento avulso: ver P2. |
| 10 | Tarefa × regra opostas | **(a) Independentes** | Sem vínculo entre elas no modelo. |
| 11 | Exibição de valores à criança | **Só representação visual** | A UI da criança não mostra número nem R$. Dois "potes": estrelas (pontos) e moedas (R$). |

## Decisões complementares (2026-10-09)

| # | Pergunta | Escolha | Consequência técnica |
|---|----------|---------|----------------------|
| B | Infra no EasyPanel | **Criar serviço PostgreSQL novo**; domínio sugerido `mesada.rafaeljrocha.cloud` | Passo a passo no README. `DATABASE_URL` por variável de ambiente. |
| P1 | Valor nas duas unidades ao mesmo tempo? | **Sim** | Campos `valor_brl` e `valor_pontos` opcionais; pelo menos um obrigatório. Uma aprovação/penalidade pode gerar até dois lançamentos (um por unidade), na mesma transação. |
| P2 | Entrega do dinheiro real sem fechamento | **PROVISÓRIO aceito**: lançamento avulso `PAGAMENTO` | Só em BRL, limitado ao saldo BRL, registrado pelo responsável. |
| P3 | Galeria de ícones padrão | **OpenMoji** (CC BY-SA 4.0) | Crédito de atribuição na área dos pais. |
| P4 | PIN parental | **Um PIN único por família** | `pin_parental_hash` em `familia`, não em `responsavel`. |
| P5 | Expiração de tarefa com janela | **No fim da janela** | Sem janela: meia-noite (America/Sao_Paulo). |
| P6 | Fluxo Git | **Uma PR por fase** | O responsável revisa e mescla pela interface web. |

## Pendências abertas na Fase 1 (PROVISÓRIO até resposta)

| # | Pergunta | Comportamento provisório implementado |
|---|----------|----------------------------------------|
| P7 | O **estorno** de um crédito pode deixar o saldo negativo (ex.: crédito de 5 estrelas já gasto em um prêmio, depois estornado por ter sido aprovado por engano)? | **Sim.** O estorno é correção de erro e não é bloqueado pelo piso zero. O ponto está isolado em `ledger.estornar()`. |
| P8 | Quantas advertências antes da penalidade (valor do padrão global, decisão 5)? | **1**, editável em Família → Regras da família. |
