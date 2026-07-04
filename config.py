"""
Configuração central da automação de extração do Bitrix24 (somente leitura).

Nenhuma credencial é armazenada aqui — a autenticação é feita manualmente
pelo usuário no navegador (ver save_auth.py) e reaproveitada via auth.json.
"""

import os

# URL base do portal Bitrix24
BASE_URL = os.environ.get("BITRIX_BASE_URL", "https://dutra.bitrix24.com.br")

# Nome do grupo/projeto do cliente, exatamente como aparece no Bitrix24
CLIENT_NAME = os.environ.get(
    "BITRIX_CLIENT_NAME", "TEC SYSTEM SISTEMAS ELETRONICOS LTDA"
)

# MODO ALTERNATIVO — grupo/projeto: ID numérico do grupo no Bitrix24.
# Só é usado quando informado (--group-id ou BITRIX_GROUP_ID); caso
# contrário o script trabalha no modo pesquisa global por nome.
_gid = os.environ.get("BITRIX_GROUP_ID", "").strip()
GROUP_ID = _gid or None

# Variações de nome do cliente, exibidas como lembrete no modo interativo
# de busca (você mesmo pesquisa esses termos dentro do Bitrix). Separar
# por vírgula em BITRIX_SEARCH_TERMS.
_terms = os.environ.get(
    "BITRIX_SEARCH_TERMS",
    "TEC SYSTEM,TECSYSTEM,TEC-SYSTEM,TECH SYSTEM,TS TELECOM",
)
SEARCH_TERMS = [t.strip() for t in _terms.split(",") if t.strip()]

# Tempo máximo (segundos) gasto rolando/paginando UMA tela confirmada no
# modo interativo antes de seguir em frente — evita loops longos e silenciosos.
SEARCH_TERM_TIMEOUT_S = float(os.environ.get("BITRIX_SEARCH_TERM_TIMEOUT_S", "40"))

# Arquivo de sessão autenticada gerado por save_auth.py.
# SENSÍVEL: está no .gitignore e NUNCA deve ser commitado.
AUTH_FILE = os.environ.get("BITRIX_AUTH_FILE", "auth.json")

# Executar sem janela visível (True) ou com navegador visível (False).
# Pode ser sobrescrito com a flag --headed em gerar_relatorio.py.
HEADLESS = os.environ.get("BITRIX_HEADLESS", "1") not in ("0", "false", "False")

# Diretório onde os relatórios gerados são salvos (também no .gitignore)
OUTPUT_DIR = os.environ.get("BITRIX_OUTPUT_DIR", "relatorios")

# Timeouts (milissegundos)
NAV_TIMEOUT_MS = int(os.environ.get("BITRIX_NAV_TIMEOUT_MS", "60000"))
ACTION_TIMEOUT_MS = int(os.environ.get("BITRIX_ACTION_TIMEOUT_MS", "15000"))

# Pausa entre aberturas de tarefas, para não sobrecarregar o portal (segundos)
DELAY_BETWEEN_TASKS_S = float(os.environ.get("BITRIX_DELAY_S", "1.0"))

# Limite de segurança de tarefas processadas por execução (0 = sem limite)
MAX_TASKS = int(os.environ.get("BITRIX_MAX_TASKS", "0"))
