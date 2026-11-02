# Roadmap do Wallet

Documento vivo para continuar o trabalho em qualquer sessão, com qualquer pessoa ou IA.
**Ao retomar:** leia este arquivo e o `CLAUDE.md`, rode `git status` e continue pelo primeiro item `[ ]` de "Agora".
**Ao terminar um item:** marque `[x]` e registre decisões relevantes.

## Objetivo

Carteira pessoal de investimentos em dark mode: importar a posição da B3, entender a distribuição por classe, categoria e subcategoria, e abrir rapidamente a análise de cada ativo no Investidor10.

## Decisões já tomadas

- Os dados antigos do banco de desenvolvimento não precisam ser preservados como referência (decisão do dono do projeto em 02/11/2026). Mesmo assim, **não apague nada sem pedir**.
- O app é somente dark mode; não há tema claro.
- O relatório da B3 é uma foto da posição: a importação reconcilia a foto com as boletas e cria só a diferença.
- A tabela `Asset` é global: categorias editadas valem para todos os usuários.

## Feito na grande atualização (02/11/2026)

- [x] Backend: `position` e `orders` retornam objetos nomeados em vez de arrays posicionais
- [x] Backend: campos para as visões (emissor, corretoras, vencimento, indexador, rendimento)
- [x] Backend: edição de categoria e subcategoria de um ativo
- [x] Backend: comando para zerar a carteira de um usuário
- [x] Backend: corrigir `GET /api/order/<id>` (lê boleta de outro usuário e não serializa)
- [x] Frontend: tema escuro, layout e componentes base; trocar `alert()` por avisos
- [x] Frontend: gráfico de pizza com navegação (classe → categoria → subcategoria → ativo)
- [x] Frontend: links para o Investidor10
- [x] Frontend: refazer dashboard, boletas, ativos, detalhe do ativo, login e perfil
- [x] Verificar no navegador, em ambiente isolado, com capturas de tela

## Feito depois (02/11/2026)

- [x] Botão de ocultar valores (`lib/privacy.tsx`); novos valores da carteira devem usar `useFormat`
- [x] Tooltip da pizza acima do valor central
- [x] Emissores: recuperados das descrições (migração `0010`), e a importação completa os que faltam
- [x] Tela de emissores com uso do limite do FGC (`/issuers`)
- [x] Filtro por classe na tabela de posições
- [x] Metas de alocação por classe e por categoria dentro da classe (`/targets`), com quanto falta em reais e resumo no dashboard

## Próximos passos

Sem ordem obrigatória; os dois primeiros têm o maior retorno.

- [ ] **Classificar ativos sem categoria:** FIIs e ações importados só têm categoria se ela já existir em `Asset` (ou for editada na tela). Avaliar preencher por `populate_asset` ou pelo Investidor10
- [ ] **Agrupar emissores por conglomerado:** bancos do mesmo grupo dividem o limite do FGC, e a tela mostra cada emissor separado
- [ ] Teto global do FGC (R$ 1 milhão por CPF a cada 4 anos) como indicador na tela de emissores
- [ ] Calculadora de aporte: dado um valor, sugerir quanto colocar em cada classe e categoria para se aproximar das metas
- [ ] Metas por subcategoria (hoje são dois níveis: classe e categoria)
- [ ] Proventos: registrar e mostrar dividendos e rendimentos
- [ ] Importar o extrato de negociação da B3, que traz data e preço reais de compra
- [ ] Atualização automática de cotações, substituindo o intervalo fixo em `populate_asset_price`
- [ ] Taxa contratada de CDB/LCI/LCA, para projetar a curva entre importações
- [ ] Indexador CDI e tipos CRI, CRA e debênture na importação
- [ ] Rentabilidade contra CDI e Ibovespa
- [ ] Trazer para o repositório o teste de navegador com Playwright (hoje foi um script temporário)

## Dívida técnica conhecida

- [ ] `consolidate`, `consolidate_fixed_income` e `daily_consolidation` usam `User.objects.get()` e falham com mais de um usuário
- [ ] Renda fixa importada só tem histórico nas datas de importação, então o total do gráfico fica abaixo do real se `consolidate` gerar linhas diárias entre elas
- [ ] Segurança: `SECRET_KEY` no código, `DEBUG=True`, `CORS_ALLOW_ALL_ORIGINS` e views com `@csrf_exempt`
- [ ] Autenticação: o cookie `currentUser` não é `HttpOnly` nem validado pelo middleware do frontend
- [ ] Dependências `latest` em `frontend/package.json`; fixar versões
- [ ] Edição de categoria em `Asset` é global e qualquer usuário autenticado pode alterar; decidir se vira dado por usuário
- [ ] Dois pacotes de gráfico (Chart.js e Highcharts); avaliar manter só um
- [ ] `frontend/Dockerfile`: a etapa final roda `npm install --production` e remove `tailwindcss` e `typescript`; `next build` falha nessa imagem. Testar se um `docker-compose up --build` com volume novo ainda sobe em modo dev
- [ ] Não testados no navegador: sessão expirada (401), filtro por corretora com mais de uma corretora e clique no nível "Ativo" da pizza
- [ ] Remover `backend/dev.py` e `backend/wallet/dev.py`
- [ ] `AssetClassificationTests` está em `wallet/tests.py`, mas testa o app `app`; mover ao criar os testes de `app`
- [ ] Testes para `app` e `user`; o frontend não tem framework de testes
- [ ] `template1` do Postgres com divergência de collation impede `manage.py test` no banco de desenvolvimento

## Como começar do zero

Os dados antigos continuam no banco. Para descartar a carteira antiga de um usuário e importar de novo:

```bash
docker exec backend python manage.py reset_portfolio --username SEU_USUARIO         # só mostra o que seria apagado
docker exec backend python manage.py reset_portfolio --username SEU_USUARIO --yes   # apaga boletas e histórico desse usuário
```

## Como verificar

- **Testes do backend:** rodar contra um Postgres descartável, nunca o banco de desenvolvimento:
  ```bash
  docker run -d --rm --name wallet_test_pg --network wallet_default -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test -e POSTGRES_DB=test postgres:16
  docker exec -e HOST=wallet_test_pg -e PORT=5432 -e USER_POSTGRES=test -e PASSWORD=test -e DB_NAME=test backend python manage.py test wallet --noinput
  docker rm -f wallet_test_pg
  ```
  O shell é zsh: escreva as flags `-e` literalmente, sem guardá-las em variável.
- **Frontend:** `docker exec frontend npx tsc --noEmit` e `docker exec frontend npm run lint`.
- **Mudou `tailwind.config.ts`?** Reinicie o contêiner (`docker restart frontend`), senão as cores novas não são geradas.
- **Visual:** abra o app e olhe. Testes automáticos não pegaram botões invisíveis nem gráficos em branco; as capturas de tela pegaram.
- **`docker-compose`:** nesta máquina precisa de `DOCKER_API_VERSION=1.44`.

## Estado do trabalho

O que está marcado como feito pode ainda não ter commit; confira com `git status`. Os ajustes locais de `docker-compose.yml` (portas e versão do Postgres) ficam fora dos commits de propósito. Commits não levam linha de coautoria.
