#!/usr/bin/env python3
"""
Gera o relatório do cliente/projeto configurado em config.py (por padrão,
"TEC SYSTEM SISTEMAS ELETRONICOS LTDA") extraindo dados do Bitrix24 pelo
navegador, em modo ESTRITAMENTE SOMENTE LEITURA.

As tarefas são localizadas pelo vínculo de CRM: o script abre a ficha da
EMPRESA no CRM (aba "Tarefas") e extrai as tarefas vinculadas a ela.
Alternativamente, use --group-id para o modo grupo/projeto.

Pré-requisito: sessão salva com `python save_auth.py` (login manual).

Uso:
    python gerar_relatorio.py [--headed] [--company-id N] [--group-id N]
                              [--max-tasks N]

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
    collect_task_ids, collect_tasks_from_company, extract_task,
    find_company_id, find_group_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headed", action="store_true",
                        help="mostra a janela do navegador durante a execução")
    parser.add_argument("--company-id", default=None,
                        help="ID da empresa no CRM (/crm/company/details/<ID>/)")
    parser.add_argument("--group-id", default=None,
                        help="modo alternativo: ID do grupo/projeto no Bitrix24")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="limita o nº de tarefas processadas (para testes)")
    parser.add_argument("--debug", action="store_true",
                        help="salva capturas de tela e lista de links em "
                             "relatorios/debug/ para diagnóstico")
    args = parser.parse_args()

    if args.company_id:
        config.COMPANY_ID = str(args.company_id)
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

            # 2) localizar o cliente e coletar as tarefas vinculadas
            company_id = None
            if args.group_id or (config.GROUP_ID and not config.COMPANY_ID):
                # modo alternativo: grupo/projeto
                group_id = find_group_id(page, log)
                task_index = collect_task_ids(page, group_id, log)
            else:
                # modo padrão: empresa no CRM (campo CRM das tarefas)
                company_id = find_company_id(page, log)
                task_index = collect_tasks_from_company(page, company_id, log)

            if args.debug:
                dbg_dir = os.path.join(config.OUTPUT_DIR, "debug")
                os.makedirs(dbg_dir, exist_ok=True)
                page.screenshot(path=os.path.join(dbg_dir, "coleta.png"),
                                full_page=True)
                with open(os.path.join(dbg_dir, "links.txt"), "w",
                          encoding="utf-8") as f:
                    for tid, info in task_index.items():
                        f.write(f"{tid}\t{info['title']}\t{info['url']}\n")
                print(f"  🐞 debug salvo em {dbg_dir}/")

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

            # 4) abrir o detalhe de cada tarefa (navegação por URL), conferir
            #    o vínculo com o cliente (campo CRM) e extrair os campos
            tasks = []
            for i, (tid, info) in enumerate(ids, 1):
                title, url = info["title"], info["url"]
                print(f"→ [{i}/{len(ids)}] tarefa {tid} — {title[:60]}")
                try:
                    tasks.append(extract_task(
                        page, tid, title, url, log,
                        expected_company_id=company_id,
                    ))
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

    # 5) mantém apenas tarefas com vínculo confirmado com o cliente (modo CRM)
    if company_id is not None:
        linked = [t for t in tasks if t.crm_linked]
        dropped = [t for t in tasks if not t.crm_linked]
        for t in dropped:
            log.warn(
                f"tarefa {t.task_id} ({t.title[:50]}) descartada: não foi "
                "possível confirmar o vínculo com o cliente no campo CRM"
            )
        if linked:
            tasks = linked
        elif dropped:
            print(
                "\n⚠️  Nenhuma tarefa teve o vínculo com o cliente confirmado "
                "no campo CRM. Nada foi descartado para não gerar relatório "
                "vazio — confira os avisos no relatório e rode com --debug."
            )

    # 6) relatório
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
