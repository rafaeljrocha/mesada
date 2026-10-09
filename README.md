# Mesada RC

Sistema familiar de mesada por mérito para crianças pequenas, organizado em tarefas, recompensas e combinados.

- **Stack:** Python 3.12, Flask, SQLAlchemy 2, Alembic (Flask-Migrate), Flask-Login, Flask-WTF, PostgreSQL, Gunicorn e Docker.
- **Decisões de produto:** [`docs/decisoes.md`](docs/decisoes.md)
- **Modelo de dados:** [`docs/modelo-dados.md`](docs/modelo-dados.md)

## Estado

| Fase | Conteúdo | Status |
|------|----------|--------|
| 0 | Decisões | Concluída |
| 1 | Fundação: autenticação, família, crianças com foto, ledger e testes | Em revisão (PR) |
| 2 | Tarefas | — |
| 3 | Regras de proibição | — |
| 4 | Recompensas | — |
| 5 | Painel e relatórios | — |
| 6 | Polimento (PWA, narração, sons) | — |

---

## Deploy no EasyPanel (passo a passo pela interface)

Domínio sugerido: `mesada.rafaeljrocha.cloud`.

### 1. Criar o banco PostgreSQL

1. No EasyPanel, abra o projeto e clique em **+ Serviço → Postgres**.
2. Use o nome `mesada-db` e deixe a senha gerada automaticamente (não reaproveite senhas de outros sistemas).
3. Clique em **Criar**. Depois, abra o serviço e copie a **URL de conexão interna** (formato `postgres://usuario:SENHA@host-interno:5432/banco`).

### 2. Criar o serviço da aplicação

1. **+ Serviço → App**, com o nome `mesada`.
2. Em **Origem**, escolha **GitHub**, repositório `rafaeljrocha/mesada`, branch `main`.
3. Em **Construção**, escolha **Dockerfile** (o arquivo fica na raiz).
4. Em **Ambiente**, cadastre as variáveis:

   | Variável | Valor |
   |----------|-------|
   | `SECRET_KEY` | 64 caracteres hexadecimais aleatórios, gerados uma única vez (peça ao Claude ou use o gerador do seu gerenciador de senhas). **Nunca troque**, porque isso desconecta todos os aparelhos. |
   | `DATABASE_URL` | URL interna copiada no passo 1 |
   | `COOKIES_SEGUROS` | `0` até o HTTPS funcionar; depois `1` |
   | `PROXY_FIX` | `1` |
   | `DATA_DIR` | `/data` |
   | `SESSAO_DIAS` | `30` |
   | `CADASTRO_ABERTO` | `0` |

5. Em **Montagens**, adicione um **Volume** com nome `mesada-dados` e caminho de montagem `/data`. É ali que ficam as fotos das crianças; sem o volume, elas se perdem a cada deploy.
6. Em **Domínios**, adicione `mesada.rafaeljrocha.cloud` com destino **HTTP, porta 8000**. Não use HTTPS no destino interno.
7. No painel DNS do domínio (Hostinger), crie um registro **A** `mesada` apontando para o IP da VPS.
8. Clique em **Implantar**. Nos logs devem aparecer `Running upgrade -> 0001` e `Listening at: http://0.0.0.0:8000`.
9. Abra `https://mesada.rafaeljrocha.cloud/healthz`. A resposta esperada é `{"status":"ok"}`.
10. Abra o domínio. Como ainda não há nenhuma família, aparece a tela **Criar família**, onde você cadastra o responsável e o PIN.
11. Com o cadeado verde no navegador, troque `COOKIES_SEGUROS` para `1` e clique em **Implantar** novamente.

### Atualizações (a cada fase)

1. **Faça backup** (veja abaixo).
2. No GitHub, abra a PR da fase e confira se o check **Testes** está verde. Depois clique em **Merge pull request → Confirm merge**.
3. No EasyPanel, abra o serviço `mesada` e clique em **Implantar**. As migrations rodam sozinhas no início.
4. Confira `/healthz` e faça login.

### Backup

- **Banco:** no serviço `mesada-db`, aba **Backups**, configure um backup diário para um destino externo (S3 ou compatível) e use o backup manual antes de cada atualização.
- **Imagens:** o volume `mesada-dados` (`/data/uploads`) também precisa de cópia periódica (backup de volume na VPS).
- Guarde a `SECRET_KEY` em um gerenciador de senhas.

### Recuperar acesso (senha esquecida)

No EasyPanel, abra o serviço `mesada` → **Console** e execute:

```
flask --app wsgi redefinir-senha email@exemplo.com
```

---

## Desenvolvimento local (opcional)

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
APP_ENV=desenvolvimento flask --app wsgi db upgrade   # usa SQLite em ./data
APP_ENV=desenvolvimento flask --app wsgi run --debug
pytest                                                  # SQLite
TEST_DATABASE_URL=postgresql://usuario:senha@localhost/mesada_teste pytest  # PostgreSQL
```

O GitHub Actions roda os testes em SQLite e em PostgreSQL a cada push e a cada PR.

## Segurança e privacidade

- As fotos são servidas apenas para usuários autenticados da mesma família, com nomes aleatórios. No upload, o metadado EXIF (inclusive a localização GPS) é removido, a imagem é redimensionada e convertida para WEBP, e o tipo é validado pelo conteúdo real do arquivo.
- Há rate limit no login e no PIN, gravado no banco para valer em todos os workers.
- Todos os formulários têm proteção CSRF. Os cookies usam `HttpOnly`, `SameSite=Lax` e `Secure` (este último quando `COOKIES_SEGUROS=1`). A CSP é restritiva, sem scripts inline e sem origens externas.
- O modo criança fica marcado na sessão do aparelho, e qualquer rota da área dos pais pede o PIN parental. O cookie "lembrar-me" não é usado de propósito, porque permitiria sair do modo criança sem PIN.
- Sobre a LGPD (isto não é parecer jurídico): todas as tabelas carregam `familia_id`, e o ledger já prevê a exclusão completa de uma família. A exportação e a exclusão de dados ainda não foram implementadas.

## Validação manual da tela da criança (tablet)

Na Fase 1, a tela da criança tem a seleção de perfil por foto e a tela inicial com os potes. Para validar:

1. Na área dos pais, toque em **Entregar à criança**.
2. A criança deve conseguir escolher o próprio perfil só pela foto, sem precisar ler.
3. A tela inicial deve mostrar a foto, o pote de estrelas e o pote de moedas, **sem números**.
4. O cadeado 🔒 deve pedir o PIN. Sem o PIN, nenhuma página da área dos pais pode abrir.

O roteiro completo de validação sem leitura será escrito na Fase 6.

## Créditos

Os ícones padrão, a partir da Fase 2, vêm do [OpenMoji](https://openmoji.org/), licença CC BY-SA 4.0.
