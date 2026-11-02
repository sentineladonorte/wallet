# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Plano e pendências:** veja `docs/ROADMAP.md` antes de começar e atualize-o ao terminar.

## Visão geral

Carteira de investimentos para ativos brasileiros (ações, FIIs e renda fixa): backend Django + frontend Next.js, atrás de um Nginx com HTTPS, orquestrados por Docker Compose.

## Comandos

### Ambiente

```bash
# Certificado autoassinado, necessário uma vez (certs/ fica fora do git)
mkdir -p certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout certs/localhost.key -out certs/localhost.crt -subj "/CN=localhost"

docker-compose up --build     # aplicação em https://localhost (nesta máquina: DOCKER_API_VERSION=1.44 docker-compose ...)
```

Arquivos não versionados que precisam existir:

- `backend/.env`, lido por `python-decouple`: `ENGINE`, `DB_NAME`, `USER_POSTGRES`, `PASSWORD`, `HOST`, `PORT` (e `ALPHAVANTAGE_KEY` para o comando `alphavantage`).
- `frontend/.env.development`: `NEXT_PUBLIC_BACKEND_URL=https://localhost/api`.

As variáveis `POSTGRES_*` do serviço `postgres` estão vazias no `docker-compose.yml` e são herdadas do ambiente em que o Compose roda.

Use o app sempre por `https://localhost`, não por `:3000`: o cookie `currentUser` é `Secure`, e o login depende dele.

### Backend (dentro de `backend/`, ou com `docker-compose exec backend ...`)

```bash
python manage.py migrate
python manage.py makemigrations
python manage.py test                          # todos os testes
python manage.py test wallet                   # um app
python manage.py test wallet.tests.MinhaClasse.test_metodo   # um único teste
flake8                                         # na raiz do repo; .flake8 define max-line-length = 120
```

Só `wallet/tests.py` tem testes; os de `app` e `user` ainda são stubs. O `flake8` não está em `requirements.txt`. A imagem Docker usa Python 3.9.

### Frontend (dentro de `frontend/`)

```bash
npm run dev
npm run build
npm run lint
```

Não há framework de testes configurado no frontend.

### Comandos de dados (`manage.py`)

| Comando | Função |
| --- | --- |
| `populate_asset` | Cadastra `Asset` a partir das APIs públicas da B3 |
| `populate_asset_price` | Importa cotações da B3 para `AssetPrice`; o intervalo de datas está fixo no código (`data_inicio`/`data_fim`), edite antes de rodar |
| `alphavantage TICKER...` | Importa cotações pela Alpha Vantage |
| `consolidate [--tickers ...]` | Recalcula o histórico de AC/FII desde a primeira compra |
| `consolidate_fixed_income [--tickers ...]` | Recalcula o histórico de renda fixa |
| `daily_consolidation` | Recalcula os últimos 10 dias |
| `reset_portfolio --username X [--yes]` | Apaga boletas e histórico do usuário; sem `--yes`, só mostra o que seria apagado |
| `backup` / `restore ARQUIVO` | `pg_dump`/`pg_restore` em `backend/backups/` |

## Arquitetura

### Roteamento

O Nginx envia `/api` ao Django (`backend:8000`) e o restante ao Next.js (`frontend:3000`). Todas as rotas estão em `backend/config/urls.py`, sem `urls.py` por app.

### Apps Django

- `app`: dados de mercado, globais e sem vínculo com usuário (`Asset`, `AssetPrice`).
- `wallet`: dados por usuário (`Order`, `AssetConsolidatedValue`) e os cálculos de posição.
- `user`: apenas views de autenticação sobre o `User` padrão do Django, sem models próprios.

Não há FK entre `wallet` e `app`: a ligação é por string, com `Order.name` igual a `Asset.ticker`/`AssetPrice.ticker`.

### Fluxo de dados

1. A importação grava `AssetPrice`, e o usuário registra `Order`s pela API.
2. Os comandos de consolidação geram uma linha diária por ativo em `AssetConsolidatedValue` (único por `user, name, date`).
3. `position_history` lê apenas essa tabela. **Nada é consolidado ao criar ou editar uma ordem**, então os gráficos históricos só mudam depois de rodar os comandos.

### Renda fixa é um caso à parte

- Ordens `RF` não têm linha em `Asset` nem em `AssetPrice`; o valor é projetado a partir de `interest_rate` por `consolidate_fixed_income`.
- Em `position`, o preço de `RF` vem de `AssetConsolidatedValue`; o dos demais tipos vem de `AssetPrice`. Sem essas linhas, o ativo aparece sem preço e fica fora dos totais.
- Ao criar uma ordem `RF`, a API grava `name` como `"<nome> <vencimento>"`. O frontend envia esse nome codificado na URL.

### Importação da posição da B3

`wallet/b3_import.py` lê o .xlsx exportado pela B3 e é exposto em `POST /api/orders/import/preview` e `/confirm`, ambos pelo mesmo `build_plan`.

- O arquivo é uma **foto da posição**, sem data nem preço de compra. A importação reconcilia a foto com as boletas por `(user, name, broker)` e cria apenas a diferença de quantidade, então reenviar o mesmo arquivo não cria boletas.
- Custos e datas são estimados e marcados em `Order.cost_estimated`, que é zerado quando `price` ou `date` são editados.
- Boletas importadas de renda fixa não têm `interest_rate`. `consolidate_fixed_income` as ignora, e o valor delas vem do `AssetConsolidatedValue` gravado na importação.
- Posição ausente do arquivo nunca é zerada automaticamente; o usuário escolhe na prévia.
- Um ativo com boletas existentes mantém a classe delas, mesmo que o arquivo classifique diferente.
- A importação grava também em `Asset` e `AssetPrice`, que são **globais** e afetam todos os usuários.

### Frontend

- Só dark mode. As cores ficam em `tailwind.config.ts` (`canvas`, `surface`, `raised`, `line`, `ink`, `soft`, `muted`, `accent`, `gain`, `loss`, `warn`); use esses nomes, não hex nem cores padrão do Tailwind. Alterar o arquivo exige reiniciar o contêiner `frontend`.
- `components/ui` tem os blocos de interface, e `useToast` substitui `alert()`. `lib/useApi.ts` faz as buscas, com estados de carregamento e erro.
- Os tipos da API estão em `src/types.ts`; `position` e `orders` retornam objetos nomeados.
- A distribuição é calculada no cliente em `lib/allocation.ts`, a partir da lista de posições: cada clique numa fatia vira um filtro, e a hierarquia é classe → categoria → subcategoria → ativo. A tabela e os indicadores do dashboard usam a mesma seleção.
- As cores das classes são fixas em `lib/assets.ts`. A paleta foi validada para o fundo escuro, e a ordem dela importa; não reordene nem gere cores novas: acima de 7 grupos, o restante vira "Outros".
- `investidor10Url` em `lib/assets.ts` monta os links por classe. Renda fixa não tem página por título no Investidor10.
- Valores da carteira são formatados com `useFormat` de `lib/privacy.tsx`, que respeita o botão de ocultar. Use `lib/format` direto só para o que não revela quanto o usuário tem. O percentual de uso do limite do FGC revela, porque o limite é público.
- Highcharts só roda no navegador; importe `charts/stock` com `next/dynamic` e `ssr: false`.

### Autenticação

- A autenticação real é a sessão do Django. O `api.ts` usa `withCredentials: true`.
- O cookie `currentUser` só é verificado por `frontend/src/middleware.ts`, para redirecionar a `/auth`; o valor não é validado.
- `api.ts` trata 401 encerrando a sessão e voltando para `/auth`; sem remover o cookie, o middleware devolveria o usuário à página atual.
- As views em `wallet` são funções Django comuns que verificam `request.user.is_authenticated` manualmente; só `user` usa decorators do DRF.

## Armadilhas

- Os comandos de consolidação usam `User.objects.get()` e falham com `MultipleObjectsReturned` quando há mais de um usuário, o que é possível desde que `/api/register` existe.
- O relatório da B3 tem dados reais de conta e posição. `posicao-*.xlsx` está no `.gitignore`, e os testes geram planilhas sintéticas.
- `daily_consolidation` não filtra `RF` nem define `asset_type`; ordens `RF` fazem `AssetPrice...latest()` lançar `DoesNotExist`.
- `backend/dev.py` e `backend/wallet/dev.py` são scripts avulsos de shell que **alteram dados de forma irreversível** (ajuste de desdobramento do BCFF11). Não os execute nem os importe.
- O banco de desenvolvimento não é descartável, e `manage.py test` não funciona nele. Rode os testes como descrito em `docs/ROADMAP.md`.
- `frontend/package.json` usa `latest` em `next`, `react` e outros, então um build novo pode trazer versões maiores.

## Convenções

Commits usam prefixos: `feat`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `ci`, `build`, `revert`, `wip`. Mensagens ao usuário nas respostas da API são em português.
