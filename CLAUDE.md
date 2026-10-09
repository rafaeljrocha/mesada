# CLAUDE.md — Mesada RC

> Memória do projeto. Trabalhe sempre em **português**. Atualize este arquivo ao concluir cada fase.

## O que é
Sistema familiar de mesada por mérito para crianças de cerca de 5 anos, com três pilares: tarefas, recompensas e regras de proibição. Há dois perfis: responsável e criança. As decisões de produto estão em `docs/decisoes.md`, que é a fonte da verdade e prevalece sobre a especificação original.

## Regras inegociáveis
1. **O ledger (`lancamento`) é imutável.** A aplicação só faz INSERT. Correções são feitas com ESTORNO ou AJUSTE_MANUAL. Saldo é sempre a soma dos lançamentos e nunca um campo editável.
2. **Toda movimentação de saldo passa por `app/services/ledger.py`**, que trava a criança com `SELECT … FOR UPDATE`.
3. **Valores monetários** usam `Decimal` e `NUMERIC(10,2)`. Nunca `float`.
4. **Datas:** grave em UTC e aplique as regras de "dia" no fuso `America/Sao_Paulo` (`app/tempo.py`).
5. **Multi-tenant:** toda consulta de domínio filtra por `familia_id`. Um recurso de outra família responde 404.
6. **Migrations:** sempre por Alembic (`flask --app wsgi db migrate`), revisadas à mão. Nunca altere uma migration já mesclada; crie uma nova. O schema dos testes vem das migrations.
7. **Não presuma decisões de produto.** Se algo não estiver decidido, implemente como configurável, registre em `docs/decisoes.md` como PROVISÓRIO e pergunte.
8. **Uma PR por fase.** O responsável revisa e mescla pela interface web do GitHub, e faz o deploy pelo EasyPanel.
9. **Tela da criança:** sem depender de leitura, com alvos de toque de pelo menos 64px, sem números de saldo (decisão 11), sem links externos.
10. **Sem JS ou CSS inline** (a CSP bloqueia). Use `app/static/js/app.js`.

## Estrutura
- `app/models/` — entidades SQLAlchemy
- `app/services/` — regras de negócio (ledger, imagens, auditoria, famílias, limite de tentativas)
- `app/routes/` — blueprints `auth`, `pais` (/pais), `crianca` (/crianca), `midia` (/midia)
- `app/acesso.py` — modo pais × modo criança e decorators
- `migrations/` — Alembic
- `tests/` — pytest; `TEST_DATABASE_URL` aponta para PostgreSQL e ativa os testes de concorrência

## Comandos
- Testes: `pytest` (SQLite) e `TEST_DATABASE_URL=postgresql://… pytest`
- Nova migration: `APP_ENV=desenvolvimento DATABASE_URL=postgresql://… flask --app wsgi db migrate -m "descricao"`
- Recuperar senha (console do EasyPanel): `flask --app wsgi redefinir-senha email`

## Estado das fases
| Fase | Status |
|------|--------|
| 0 — Decisões | Concluída |
| 1 — Fundação | Em revisão |
| 2 — Tarefas | Pendente |
| 3 — Regras de proibição | Pendente |
| 4 — Recompensas | Pendente |
| 5 — Painel e relatórios | Pendente |
| 6 — Polimento | Pendente |
