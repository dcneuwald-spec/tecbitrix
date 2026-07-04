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

# ID numérico da EMPRESA no CRM (opcional). É o número na URL da ficha:
#   https://dutra.bitrix24.com.br/crm/company/details/<ID>/
# Se vazio, o script tenta localizar a empresa pelo nome na lista do CRM.
# TEC SYSTEM SISTEMAS ELETRONICOS LTDA = 639
#   (https://dutra.bitrix24.com.br/crm/company/details/639/)
_cid = os.environ.get("BITRIX_COMPANY_ID", "").strip()
COMPANY_ID = _cid or "639"

# MODO ALTERNATIVO — grupo/projeto: ID numérico do grupo no Bitrix24.
# Só é usado quando informado (--group-id ou BITRIX_GROUP_ID); caso
# contrário o script trabalha no modo CRM (empresa) acima.
_gid = os.environ.get("BITRIX_GROUP_ID", "").strip()
GROUP_ID = _gid or None

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
