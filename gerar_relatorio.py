#!/usr/bin/env python3
"""
Gera o relatório do cliente/projeto configurado em config.py (por padrão,
"TEC SYSTEM SISTEMAS ELETRONICOS LTDA") extraindo dados do Bitrix24 pelo
navegador, em modo ESTRITAMENTE SOMENTE LEITURA.

As tarefas são localizadas por PESQUISA GLOBAL por nome (variações de nome
configuradas em config.SEARCH_TERMS). Alternativamente, use --group-id para
o modo grupo/projeto.

Pré-requisito: sessão salva com `python save_auth.py` (login manual).

Uso:
    python gerar_relatorio.py [--headed] [--group-id N] [--max-tasks N]

Saída: relatorios/relatorio_AAAA-MM-DD.md e relatorios/tarefas_AAAA-MM-DD.csv
"""

import argparse
import os
import sys
from datetime import date

from playwright.sync_api import sync_playwright

import config
from bitrix_readonly.auth import SessionExpired, check_session, require_auth_file
from bitrix_readonly.guard import GuardLog, ReadOnlyViolation, install_network_guard
from bitrix_readonly.report import build_report, previous_month_range
from bitrix_readonly.scraper import (
    collect_task_ids, collect_tasks_by_search, extract_task, find_group_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headed", action="store_true",
                        help="mostra a janela do navegador durante a execução")
    parser.add_argument("--group-id", default=None,
                        help="modo alternativo: ID do grupo/projeto no Bitrix24")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="limita o nº de tarefas processadas (para testes)")
    parser.add_argument("--debug", action="store_true",
                        help="salva capturas de tela e lista de links em "
                             "relatorios/debug/ para diagnóstico")
    args = parser.parse_args()

    if args.group_id:
        config.GROUP_ID = str(args.group_id)
    if args.max_tasks is not None:
        config.MAX_TASKS = args.max_tasks
    headless = config.HEADLESS and not args.headed

    today = date.today()
    pm_start, pm_end = previous_month_range(today)
    print("=" * 70)
    print(f"RELATÓRIO BITRIX24 (somente leitura) — {config.CLIENT_NAME}")
    print(f"Tarefas: 01/01/{today.year} a {today:%d/%m/%Y} | "
          f"Horas: {pm_start:%d/%m/%Y} a {pm_end:%d/%m/%Y}")
    print("=" * 70)

    try:
        auth_file = require_auth_file()
    except SessionExpired as e:
        print(f"\n❌ {e}")
        return 2

    log = GuardLog()

    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel="chrome", headless=headless)
            except Exception:
                browser = pw.chromium.launch(headless=headless)

            context = browser.new_context(storage_state=auth_file)
            context.set_default_timeout(config.ACTION_TIMEOUT_MS)
            context.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)

            # Guarda somente-leitura: bloqueia qualquer requisição de escrita
            install_network_guard(context, log)

            page = context.new_page()

            # 1) sessão válida?
            check_session(page)
            print("✓ Sessão autenticada válida (nenhuma credencial usada).")

            # 2) coletar as tarefas
            if args.group_id or config.GROUP_ID:
                # modo alternativo: grupo/projeto
                group_id = find_group_id(page, log)
                task_index = collect_task_ids(page, group_id, log)
            else:
                # modo padrão: pesquisa global pelas variações de nome
                # (TEC SYSTEM, TECSYSTEM, TS TELECOM…)
                task_index = collect_tasks_by_search(page, log)

            if args.debug or not task_index:
                dbg_dir = os.path.join(config.OUTPUT_DIR, "debug")
                os.makedirs(dbg_dir, exist_ok=True)
                try:
                    page.screenshot(path=os.path.join(dbg_dir, "coleta.png"),
                                    full_page=True)
                except Exception:
                    pass
                with open(os.path.join(dbg_dir, "links.txt"), "w",
                          encoding="utf-8") as f:
                    f.write("== FRAMES DA PÁGINA ==\n")
                    for fr in page.frames:
                        f.write(f"frame: {fr.url}\n")
                    f.write("\n== TAREFAS COLETADAS ==\n")
                    for tid, info in task_index.items():
                        f.write(f"{tid}\t{info['title']}\t{info['url']}\n")
                print(f"  🐞 debug salvo em {dbg_dir}/ (coleta.png, links.txt)")

            if not task_index:
                print("\n❌ Nenhuma tarefa encontrada — relatório não gerado.")
                return 3

            ids = list(task_index.items())
            if config.MAX_TASKS and len(ids) > config.MAX_TASKS:
                log.warn(
                    f"processando apenas {config.MAX_TASKS} de {len(ids)} "
                    "tarefas (limite --max-tasks)"
                )
                ids = ids[: config.MAX_TASKS]

            # 3) abrir o detalhe de cada tarefa (navegação por URL) e extrair os campos
            tasks = []
            for i, (tid, info) in enumerate(ids, 1):
                title, url = info["title"], info["url"]
                print(f"→ [{i}/{len(ids)}] tarefa {tid} — {title[:60]}")
                try:
                    t = extract_task(page, tid, title, url, log)
                    tasks.append(t)
                except ReadOnlyViolation:
                    raise
                except Exception as e:
                    log.warn(f"falha ao extrair tarefa {tid}: {e}")

            browser.close()

    except ReadOnlyViolation as e:
        print("\n" + "=" * 70)
        print("🔒 EXECUÇÃO INTERROMPIDA PELA GUARDA SOMENTE-LEITURA")
        print("=" * 70)
        print(str(e))
        print("\nNenhum dado foi alterado no Bitrix24. Revise o passo indicado "
              "acima antes de executar novamente.")
        return 10
    except SessionExpired as e:
        print(f"\n❌ {e}")
        return 2
    except RuntimeError as e:
        # ex.: empresa/projeto não localizado — mensagem já explica o que fazer
        print(f"\n❌ {e}")
        return 4
    except Exception as e:
        print("\n❌ Erro inesperado durante a extração:")
        print(f"   {type(e).__name__}: {e}")
        print("   Nenhum dado foi alterado no Bitrix24 (somente leitura).")
        print("   Rode teste.bat novamente; se o erro persistir, envie a "
              "mensagem acima e o conteúdo de relatorios\\debug\\.")
        return 1

    # 4) gerar relatório
    result = build_report(tasks, log, today)

    print("\n" + "=" * 70)
    print("✅ RELATÓRIO GERADO")
    print("=" * 70)
    print(f"Tarefas no ano:            {result['tasks_in_scope']}")
    print(f"Horas em {result['prev_month_label']:<12}      {result['prev_month_hours']}")
    print(f"Aguardando ação sem horas: {result['critical']}")
    print(f"\nArquivos:\n  - {result['md']}\n  - {result['csv']}")
    if log.blocked_requests:
        print(
            f"\n🔒 Atenção: {len(log.blocked_requests)} requisição(ões) de "
            "escrita foram BLOQUEADAS (nada foi alterado). Detalhes na seção "
            "'Integridade da extração' do relatório."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
