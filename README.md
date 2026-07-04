# Relatório Bitrix24 — TEC SYSTEM (somente leitura)

Automação com **Playwright + Chrome** que acessa o Bitrix24
(`https://dutra.bitrix24.com.br/online/`) com uma sessão já autenticada e
extrai os dados do cliente **TEC SYSTEM SISTEMAS ELETRONICOS LTDA**
para gerar um relatório de tarefas e horas.

As tarefas são localizadas pelo **vínculo de CRM**: o script encontra a
empresa do cliente no CRM, abre a ficha dela
(`/crm/company/details/<ID>/`), entra na aba **Tarefas** e extrai as
tarefas vinculadas. (Há também um modo alternativo por grupo/projeto,
via `--group-id`.)

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

Além disso, **nenhum filtro é salvo no Bitrix**: o script lê a lista de
tarefas vinculadas à empresa na ficha do CRM (rolagem/paginação e troca de
aba, que são ações de navegação) e aplica os recortes de período
**localmente, em Python**. A abertura do detalhe de cada tarefa é feita
**por URL direta** (navegação), não por botões de ação.

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
python gerar_relatorio.py --company-id 123  # pula a busca da empresa pelo nome
python gerar_relatorio.py --group-id 456    # modo alternativo: grupo/projeto
python gerar_relatorio.py --max-tasks 5     # execução de teste com poucas tarefas
python gerar_relatorio.py --debug           # salva diagnóstico em relatorios/debug/
```

Configurações (nome do cliente, URL, timeouts…) ficam em `config.py` e podem
ser sobrescritas por variáveis de ambiente (`BITRIX_COMPANY_ID`,
`BITRIX_CLIENT_NAME`, `BITRIX_HEADLESS=0`, …).

> **Dica:** para acelerar e evitar ambiguidades, abra a empresa no CRM do
> Bitrix, copie o número da URL `/crm/company/details/<ID>/` e use
> `--company-id <ID>`.

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
  scraper.py                 # navegação e extração (CRM/empresa, lista, detalhe)
  report.py                  # períodos, tradução de status, MD + CSV
```

## Limitações conhecidas

- Seletores de UI do Bitrix24 mudam entre versões/idiomas. O extrator usa
  múltiplos fallbacks e busca por rótulos de texto (PT/EN); o que não puder
  ser lido vira **aviso** no relatório — o script não inventa dados.
- A coleta considera as tarefas **vinculadas à empresa no campo CRM**
  exibidas na aba "Tarefas" da ficha da empresa. Tarefas sem esse vínculo
  não aparecem — nesse caso use o modo `--group-id`.
- O detalhamento de horas por mês depende da lista de apontamentos exibida na
  página da tarefa; quando só o total agregado ("Tempo gasto") está visível,
  o total é usado e a coluna do mês anterior fica 0:00 com aviso.
