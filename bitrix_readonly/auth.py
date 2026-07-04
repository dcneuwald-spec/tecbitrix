"""
Gestão de sessão autenticada — SEM credenciais no código.

Fluxo:
- save_auth.py abre o navegador visível, o usuário faz login MANUALMENTE e o
  estado de sessão (cookies/localStorage) é salvo em auth.json.
- As execuções seguintes carregam auth.json via storage_state.
- Se a sessão expirar, SessionExpired é lançada e o usuário é orientado a
  rodar save_auth.py novamente. O script NUNCA preenche login/senha.
"""

from __future__ import annotations

import os

import config


class SessionExpired(RuntimeError):
    """Sessão do Bitrix24 inválida/expirada — requer novo login manual."""


LOGIN_HINTS = ("/auth", "/login", "bitrix24.net/oauth", "/passport/")


def is_login_page(page) -> bool:
    """Heurística para detectar tela de login (sessão ausente/expirada)."""
    url = (page.url or "").lower()
    if any(h in url for h in LOGIN_HINTS):
        return True
    try:
        # Campo de senha visível => tela de autenticação
        pwd = page.locator("input[type='password']")
        if pwd.count() > 0 and pwd.first.is_visible():
            return True
    except Exception:
        pass
    return False


def require_auth_file() -> str:
    if not os.path.exists(config.AUTH_FILE):
        raise SessionExpired(
            f"Arquivo de sessão '{config.AUTH_FILE}' não encontrado.\n"
            "Execute primeiro:  python save_auth.py\n"
            "(será aberto o navegador para você fazer login manualmente; "
            "o script não pede nem armazena senha)"
        )
    return config.AUTH_FILE


def check_session(page) -> None:
    """Navega até o portal e confirma que a sessão salva ainda é válida."""
    page.goto(f"{config.BASE_URL}/online/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if is_login_page(page):
        raise SessionExpired(
            "A sessão salva em auth.json expirou (o portal redirecionou para "
            "a tela de login).\n"
            "Execute novamente:  python save_auth.py\n"
            "e faça o login manualmente no navegador. Nenhuma credencial é "
            "digitada ou armazenada pelo script."
        )
