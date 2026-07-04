# Relatório Bitrix24 — TEC SYSTEM (somente leitura)

Automação com **Playwright + Chrome** que acessa o Bitrix24
(`https://dutra.bitrix24.com.br/online/`) com uma sessão já autenticada e
extrai os dados do cliente **TEC SYSTEM SISTEMAS ELETRONICOS LTDA**
para gerar um relatório de tarefas e horas.

As tarefas são localizadas por **pesquisa global pelo nome do cliente**: o
script navega para `/search/?q=<termo>` com cada variação de nome
configurada (`config.SEARCH_TERMS` — ex.: TEC SYSTEM, TECSYSTEM, TECH
SYSTEM, TS TELECOM) e coleta os links de tarefas encontrados nos
resultados. (Há também um modo alternativo por grupo/projeto, via
`--group-id`.)

Cada termo tem um tempo máximo de busca (`SEARCH_TERM_TIMEOUT_S`, padrão
40s) e, se não encontrar nenhuma tarefa, o script salva automaticamente um
screenshot + texto da página em `relatorios/debug/busca_<termo>.png/.txt`
para diagnóstico — mesmo sem a flag `--debug`.

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

Além disso, **nenhum filtro é salvo no Bitrix**: o script lê os resultados
da pesquisa global por nome (rolagem/paginação e troca de aba, que são
ações de navegação) e aplica os recortes de período **localmente, em
Python**. A abertura do detalhe de cada tarefa é feita **por URL direta**
(navegação), não por botões de ação.

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

## Uso no Windows (recomendado): arquivos .bat

Basta dar dois cliques (ou digitar o nome no Prompt de Comando), na ordem:

| Arquivo | O que faz |
|---|---|
| `instalar.bat` | 1ª vez: cria o ambiente Python e instala as dependências |
| `login.bat` | abre o navegador para o login manual no Bitrix24 (salva `auth.json`) |
| `teste.bat` | rodada de validação: 10 tarefas, navegador visível, com debug |
| `relatorio.bat` | relatório completo (aceita opções, ex.: `relatorio.bat --headed`) |
| `atualizar.bat` | baixa e aplica a versão mais recente do GitHub |

## Instalação manual (Linux/Mac ou quem preferir)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium    # dispensável se o Chrome já estiver instalado
```

## Uso manual

```bash
# 1ª vez (ou quando a sessão expirar): login manual e captura da sessão
python save_auth.py

# Gerar o relatório
python gerar_relatorio.py

# Opções úteis
python gerar_relatorio.py --headed          # com janela visível
python gerar_relatorio.py --group-id 456    # modo alternativo: grupo/projeto
python gerar_relatorio.py --max-tasks 5     # execução de teste com poucas tarefas
python gerar_relatorio.py --debug           # salva diagnóstico em relatorios/debug/
```

Configurações (nome do cliente, termos de busca, URL, timeouts…) ficam em
`config.py` e podem ser sobrescritas por variáveis de ambiente
(`BITRIX_SEARCH_TERMS`, `BITRIX_CLIENT_NAME`, `BITRIX_HEADLESS=0`, …).

> **Dica:** se a pesquisa por nome não encontrar as tarefas certas, ajuste
> as variações de nome em `BITRIX_SEARCH_TERMS` (separadas por vírgula) ou
> confira os arquivos `relatorios/debug/busca_<termo>.png/.txt`, salvos
> automaticamente sempre que um termo não retornar nenhuma tarefa.

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
  scraper.py                 # navegação e extração (pesquisa por nome, lista, detalhe)
  report.py                  # períodos, tradução de status, MD + CSV
```

## Limitações conhecidas

- Seletores de UI do Bitrix24 mudam entre versões/idiomas. O extrator usa
  múltiplos fallbacks e busca por rótulos de texto (PT/EN); o que não puder
  ser lido vira **aviso** no relatório — o script não inventa dados.
- A coleta depende da **pesquisa global do Bitrix24** (`/search/?q=`)
  encontrar as tarefas pelo nome do cliente no título/descrição. Tarefas
  sem nenhuma variação do nome no texto não aparecem — nesse caso use o
  modo `--group-id` ou ajuste `BITRIX_SEARCH_TERMS`.
- O detalhamento de horas por mês depende da lista de apontamentos exibida na
  página da tarefa; quando só o total agregado ("Tempo gasto") está visível,
  o total é usado e a coluna do mês anterior fica 0:00 com aviso.
