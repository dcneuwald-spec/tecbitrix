# Relatório Bitrix24 — TEC SYSTEM (somente leitura)

Automação com **Playwright + Chrome** que acessa o Bitrix24
(`https://dutra.bitrix24.com.br/online/`) com uma sessão já autenticada e
extrai os dados do projeto/cliente **TEC SYSTEM SISTEMAS ELETRONICOS LTDA**
para gerar um relatório de tarefas e horas.

> Esta versão usa automação de **navegador** (Playwright), conforme
> solicitado — **não** usa API REST nem webhooks do Bitrix24.

## 🔒 Premissa crítica — somente leitura

O script **apenas navega, visualiza e extrai** dados. Ele **nunca** cria,
edita, conclui, move ou exclui nada. Duas camadas de proteção garantem isso:

1. **Guarda de rede** (`bitrix_readonly/guard.py`): toda requisição do
   navegador é interceptada; chamadas ajax do Bitrix cuja ação contenha um
   verbo de escrita (`add`, `update`, `delete`, `complete`, `save`, `set`…)
   e métodos HTTP `PUT/PATCH/DELETE` são **bloqueados antes de sair do
   navegador** e registrados no relatório.
2. **Clique seguro**: antes de qualquer clique, o texto/aria-label/title do
   elemento é verificado contra uma lista de palavras de ação de escrita
   (salvar, editar, concluir, excluir, aprovar, criar, adicionar…). Se houver
   correspondência — ou dúvida —, o script **não clica**, interrompe a
   execução e reporta o motivo ao usuário (`ReadOnlyViolation`).

Além disso, **nenhum filtro é salvo no Bitrix**: o script carrega a lista de
tarefas do grupo (rolagem/paginação, que são ações de navegação) e aplica os
recortes de período **localmente, em Python**. A abertura do detalhe de cada
tarefa é feita **por URL direta** (navegação), não por botões de ação.

## 🔑 Autenticação — sem senha no código

- O script **nunca** pede, digita ou armazena usuário/senha.
- Na primeira execução, `save_auth.py` abre o navegador **visível** e você
  faz o login manualmente (incluindo 2FA). Depois, apenas o estado de sessão
  (cookies) é salvo em `auth.json` via `context.storage_state()`.
- As execuções seguintes reabrem a sessão a partir de `auth.json`.
- Se a sessão expirar, o script detecta o redirecionamento para a tela de
  login, **para**, e pede para você rodar `save_auth.py` de novo.
- `auth.json` é **sensível** (dá acesso à sua conta): já está no
  `.gitignore` — nunca commitar nem compartilhar.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium    # dispensável se o Chrome já estiver instalado
```

## Uso

```bash
# 1ª vez (ou quando a sessão expirar): login manual e captura da sessão
python save_auth.py

# Gerar o relatório
python gerar_relatorio.py

# Opções úteis
python gerar_relatorio.py --headed          # com janela visível
python gerar_relatorio.py --group-id 123    # pula a busca do projeto pelo nome
python gerar_relatorio.py --max-tasks 5     # execução de teste com poucas tarefas
```

Configurações (nome do cliente, URL, timeouts…) ficam em `config.py` e podem
ser sobrescritas por variáveis de ambiente (`BITRIX_GROUP_ID`,
`BITRIX_CLIENT_NAME`, `BITRIX_HEADLESS=0`, …).

> **Dica:** para acelerar e evitar ambiguidades, abra o projeto no Bitrix,
> copie o número da URL `/workgroups/group/<ID>/` e use `--group-id <ID>`.

## O que o relatório contém

Saída em `relatorios/relatorio_AAAA-MM-DD.md` (+ CSV com a tabela):

1. **Resumo executivo** — total de tarefas do ano (desde 1º/jan), totais por
   status (traduzidos para português), horas apontadas **somente no mês
   anterior** (calculado dinamicamente) e a contagem de tarefas aguardando
   ação sem nenhuma hora.
2. **Tabela de tarefas** (ano completo até hoje) — ID, título, status,
   responsável, criação, prazo, conclusão, horas totais acumuladas, horas
   **só do mês anterior** (coluna separada) e resumo da atividade em 1–2
   frases (usa os últimos comentários quando a descrição é vaga).
3. **⚠️ Seção crítica** — tarefas em status de espera/pendência (aguardando
   ação, nova, adiada, aguardando controle) com **zero horas** apontadas no
   total: itens completamente parados.
4. **Integridade da extração** — avisos de campos ilegíveis, tarefas fora do
   recorte e a lista de eventuais requisições de escrita **bloqueadas** pela
   guarda (se houver alguma, nada chegou ao servidor, mas o fluxo deve ser
   revisado).

### Critérios adotados

- **Recorte anual:** tarefas com **data de criação** ≥ 1º de janeiro do ano
  corrente. Tarefas cuja data de criação não pôde ser lida são **incluídas**
  com aviso (nunca descartadas em silêncio).
- **Horas do mês anterior:** soma dos apontamentos de tempo cuja data cai
  entre o primeiro e o último dia do mês anterior à execução.
- **"Atrasada":** anexado ao status quando o prazo venceu e a tarefa não foi
  concluída.

## Estrutura

```
config.py                    # URL, cliente, timeouts (sem credenciais)
save_auth.py                 # 1ª execução: login manual + storage_state
gerar_relatorio.py           # entrada principal
bitrix_readonly/
  guard.py                   # guarda somente-leitura (rede + clique seguro)
  auth.py                    # validação de sessão / detecção de expiração
  scraper.py                 # navegação e extração (grupo, lista, detalhe)
  report.py                  # períodos, tradução de status, MD + CSV
```

## Limitações conhecidas

- Seletores de UI do Bitrix24 mudam entre versões/idiomas. O extrator usa
  múltiplos fallbacks e busca por rótulos de texto (PT/EN); o que não puder
  ser lido vira **aviso** no relatório — o script não inventa dados.
- Se a visão padrão do grupo estiver em Kanban/Prazos e nenhum link de tarefa
  for encontrado, alterne manualmente para a visão **Lista** uma vez (isso é
  uma preferência sua de visualização) e execute novamente.
- O detalhamento de horas por mês depende da lista de apontamentos exibida na
  página da tarefa; quando só o total agregado ("Tempo gasto") está visível,
  o total é usado e a coluna do mês anterior fica 0:00 com aviso.
