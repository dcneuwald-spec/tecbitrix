#!/usr/bin/env python3
"""
PRIMEIRA EXECUÇÃO — captura de sessão autenticada (login 100% manual).

Abre o Chrome visível em https://dutra.bitrix24.com.br/online/ e aguarda VOCÊ
fazer o login manualmente (usuário, senha, 2FA — tudo digitado por você no
navegador). Depois disso, salva apenas o estado de sessão (cookies) em
auth.json para as execuções seguintes.

O script NUNCA lê, digita ou armazena usuário/senha.
auth.json é sensível: já está no .gitignore — não commitar nem compartilhar.
"""

import sys

from playwright.sync_api import sync_playwright

import config
from bitrix_readonly.auth import is_login_page


def main() -> int:
    print("=" * 70)
    print("CAPTURA DE SESSÃO DO BITRIX24 — LOGIN MANUAL")
    print("=" * 70)
    print(f"Portal: {config.BASE_URL}/online/")
    print()
    print("1. O navegador vai abrir agora (janela visível).")
    print("2. Faça o login manualmente (incluindo 2FA, se houver).")
    print("3. Quando estiver dentro do Bitrix24, volte aqui e pressione ENTER.")
    print()

    with sync_playwright() as pw:
        # tenta o Chrome instalado; se não houver, usa o Chromium do Playwright
        try:
            browser = pw.chromium.launch(channel="chrome", headless=False)
        except Exception:
            print("(Chrome não encontrado — usando Chromium do Playwright)")
            browser = pw.chromium.launch(headless=False)

        context = browser.new_context()
        page = context.new_page()
        page.goto(f"{config.BASE_URL}/online/", wait_until="domcontentloaded")

        input(">>> Pressione ENTER depois de concluir o login no navegador... ")

        page.wait_for_timeout(2000)
        if is_login_page(page):
            print()
            print("❌ Ainda parece estar na tela de login — sessão NÃO salva.")
            print("   Conclua o login no navegador e rode este script de novo.")
            browser.close()
            return 1

        context.storage_state(path=config.AUTH_FILE)
        browser.close()

    print()
    print(f"✅ Sessão salva em '{config.AUTH_FILE}'.")
    print("   Este arquivo dá acesso à sua conta: NÃO commitar, NÃO compartilhar.")
    print("   Agora execute:  python gerar_relatorio.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
