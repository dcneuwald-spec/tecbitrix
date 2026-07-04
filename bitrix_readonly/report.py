"""
Geração do relatório (Markdown + CSV) a partir das tarefas extraídas.

Recortes de período:
- TAREFAS: criadas desde 1º de janeiro do ano corrente até hoje.
- HORAS: apontamentos feitos no MÊS ANTERIOR (calculado dinamicamente).
"""

from __future__ import annotations

import csv
import os
import re
import unicodedata
from datetime import date

import config
from .guard import GuardLog
from .scraper import Task, format_hours


# ---------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------

def year_start(today: date | None = None) -> date:
    today = today or date.today()
    return date(today.year, 1, 1)


def previous_month_range(today: date | None = None) -> tuple[date, date]:
    """(primeiro dia, último dia) do mês anterior à data de execução."""
    today = today or date.today()
    first_this_month = date(today.year, today.month, 1)
    last_prev = date.fromordinal(first_this_month.toordinal() - 1)
    first_prev = date(last_prev.year, last_prev.month, 1)
    return first_prev, last_prev


MONTH_NAMES_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# ---------------------------------------------------------------------------
# Tradução/normalização de status
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower().strip())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")

STATUS_MAP = {
    # inglês -> português (caso a UI esteja em EN)
    "completed": "Concluída",
    "in progress": "Em andamento",
    "pending": "Aguardando ação",
    "waiting": "Aguardando ação",
    "supposedly completed": "Aguardando controle",
    "deferred": "Adiada",
    "new": "Nova",
    "overdue": "Atrasada",
    # variantes PT normalizadas -> forma canônica
    "concluida": "Concluída",
    "concluido": "Concluída",
    "em andamento": "Em andamento",
    "aguardando acao": "Aguardando ação",
    "aguarda execucao": "Aguardando ação",
    "pendente": "Aguardando ação",
    "aguardando controle": "Aguardando controle",
    "supostamente concluida": "Aguardando controle",
    "adiada": "Adiada",
    "nova": "Nova",
    "nao iniciada": "Nova",
    "atrasada": "Atrasada",
}

# Status considerados "em espera/pendência" para a seção crítica
WAITING_STATUSES = {"Aguardando ação", "Nova", "Adiada", "Aguardando controle"}
DONE_STATUSES = {"Concluída"}


def translate_status(task: Task, today: date | None = None) -> str:
    today = today or date.today()
    raw = _norm(task.status)
    label = None
    for key, value in STATUS_MAP.items():
        if raw == key or raw.startswith(key):
            label = value
            break
    if label is None:
        label = task.status.strip() or "(não identificado)"

    # marca atraso: prazo vencido e não concluída
    if (
        label not in DONE_STATUSES
        and task.deadline
        and task.deadline < today
        and not task.closed
    ):
        if label == "(não identificado)":
            label = "Atrasada"
        elif "atrasada" not in label.lower():
            label = f"{label} (atrasada)"
    return label


# ---------------------------------------------------------------------------
# Resumo da atividade (descrição/comentários em 1-2 frases)
# ---------------------------------------------------------------------------

def activity_summary(task: Task) -> str:
    text = (task.description or "").strip()
    # descrição vaga/curta -> usa últimos comentários
    if len(text) < 30 and task.last_comments:
        text = " • ".join(task.last_comments[-2:])
    if not text:
        return "(sem descrição ou comentários legíveis)"
    text = re.sub(r"\s+", " ", text)
    # corta em ~2 frases ou 220 caracteres
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:2])
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "…"
    return summary


# ---------------------------------------------------------------------------
# Montagem do relatório
# ---------------------------------------------------------------------------

def _fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def build_report(tasks: list, log: GuardLog, today: date | None = None) -> dict:
    """Filtra, agrega e escreve relatório .md e .csv. Retorna caminhos."""
    today = today or date.today()
    y_start = year_start(today)
    pm_start, pm_end = previous_month_range(today)
    pm_label = f"{MONTH_NAMES_PT[pm_start.month]}/{pm_start.year}"

    # Recorte do ano: criadas desde 1º/jan. Tarefas com data de criação
    # ilegível são INCLUÍDAS com aviso (nunca descartar silenciosamente).
    in_scope, skipped = [], []
    for t in tasks:
        if t.created is None:
            t.warnings.append(
                "data de criação não lida — tarefa incluída por precaução"
            )
            in_scope.append(t)
        elif t.created >= y_start:
            in_scope.append(t)
        else:
            skipped.append(t)

    # Agregados
    status_count: dict = {}
    total_prev_month = 0
    rows = []
    for t in in_scope:
        label = translate_status(t, today)
        base_label = label.replace(" (atrasada)", "")
        status_count[base_label] = status_count.get(base_label, 0) + 1
        prev_secs = t.seconds_in_period(pm_start, pm_end)
        total_prev_month += prev_secs
        rows.append((t, label, prev_secs))

    # Seção crítica: aguardando ação/nova/adiada e 0 horas no total
    critical = [
        (t, label) for (t, label, _p) in rows
        if label.replace(" (atrasada)", "") in WAITING_STATUSES
        and t.total_seconds == 0
    ]

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    stamp = today.strftime("%Y-%m-%d")
    md_path = os.path.join(config.OUTPUT_DIR, f"relatorio_{stamp}.md")
    csv_path = os.path.join(config.OUTPUT_DIR, f"tarefas_{stamp}.csv")

    # ----- Markdown -----
    lines = []
    lines.append(f"# Relatório — {config.CLIENT_NAME}")
    lines.append("")
    lines.append(f"- **Gerado em:** {today.strftime('%d/%m/%Y')}")
    lines.append(
        f"- **Período de tarefas:** {_fmt_date(y_start)} a {_fmt_date(today)}"
    )
    lines.append(
        f"- **Período de horas detalhadas:** {pm_label} "
        f"({_fmt_date(pm_start)} a {_fmt_date(pm_end)})"
    )
    lines.append("- **Modo de extração:** navegador (Playwright), "
                 "somente leitura — nenhum dado foi alterado no Bitrix24.")
    lines.append("")

    lines.append("## 1. Resumo executivo")
    lines.append("")
    lines.append(f"| Indicador | Valor |")
    lines.append(f"|---|---|")
    lines.append(f"| Tarefas no ano ({today.year}) | **{len(in_scope)}** |")
    for label in sorted(status_count, key=lambda k: -status_count[k]):
        lines.append(f"| — {label} | {status_count[label]} |")
    lines.append(
        f"| Horas apontadas em {pm_label} | **{format_hours(total_prev_month)}** |"
    )
    lines.append(
        f"| Tarefas aguardando ação SEM horas apontadas | **{len(critical)}** |"
    )
    lines.append("")

    lines.append("## 2. Tabela de tarefas (ano completo até hoje)")
    lines.append("")
    lines.append(
        "| ID | Título | Status | Responsável | Criação | Prazo | Conclusão "
        f"| Horas totais | Horas {pm_label} | Resumo da atividade |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for t, label, prev_secs in sorted(
        rows, key=lambda r: (r[0].created or date.min), reverse=True
    ):
        def esc(s: str) -> str:
            return (s or "").replace("|", "\\|")
        lines.append(
            f"| {t.task_id} | {esc(t.title)} | {label} | {esc(t.responsible) or '—'} "
            f"| {_fmt_date(t.created)} | {_fmt_date(t.deadline)} "
            f"| {_fmt_date(t.closed)} | {format_hours(t.total_seconds)} "
            f"| {format_hours(prev_secs)} | {esc(activity_summary(t))} |"
        )
    lines.append("")

    lines.append("## 3. ⚠️ CRÍTICO — Tarefas aguardando ação sem nenhuma hora apontada")
    lines.append("")
    if critical:
        lines.append(
            "Itens completamente parados: em status de espera/pendência e "
            "com **zero horas** de trabalho registradas desde a criação."
        )
        lines.append("")
        lines.append("| ID | Título | Status | Responsável | Criação | Prazo |")
        lines.append("|---|---|---|---|---|---|")
        for t, label in critical:
            lines.append(
                f"| {t.task_id} | {(t.title or '').replace('|', '·')} | {label} "
                f"| {t.responsible or '—'} | {_fmt_date(t.created)} "
                f"| {_fmt_date(t.deadline)} |"
            )
    else:
        lines.append("Nenhuma tarefa nessa condição. ✅")
    lines.append("")

    # ----- Avisos e integridade -----
    lines.append("## 4. Integridade da extração")
    lines.append("")
    if skipped:
        lines.append(
            f"- {len(skipped)} tarefa(s) do grupo ficaram fora do recorte "
            f"por terem sido criadas antes de {_fmt_date(y_start)}."
        )
    all_warnings = list(log.warnings)
    for t in in_scope:
        for w in t.warnings:
            all_warnings.append(f"tarefa {t.task_id} ({t.title[:40]}): {w}")
    if all_warnings:
        lines.append(f"- {len(all_warnings)} aviso(s) de leitura:")
        for w in all_warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("- Nenhum aviso de leitura. ✅")
    if log.blocked_requests:
        lines.append("")
        lines.append(
            "### 🔒 Requisições de escrita BLOQUEADAS pela guarda de segurança"
        )
        lines.append(
            "As requisições abaixo foram interceptadas e **não chegaram ao "
            "servidor** (nenhum dado foi alterado), mas indicam um fluxo "
            "inesperado que deve ser revisado:"
        )
        for b in log.blocked_requests:
            lines.append(f"- {b}")
    else:
        lines.append("- Nenhuma tentativa de escrita detectada/bloqueada. ✅")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ----- CSV -----
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "ID", "Título", "Status", "Responsável", "Data de criação",
            "Prazo", "Data de conclusão", "Horas totais",
            f"Horas {pm_label}", "Resumo da atividade", "URL",
        ])
        for t, label, prev_secs in rows:
            writer.writerow([
                t.task_id, t.title, label, t.responsible,
                _fmt_date(t.created), _fmt_date(t.deadline),
                _fmt_date(t.closed), format_hours(t.total_seconds),
                format_hours(prev_secs), activity_summary(t), t.url,
            ])

    return {
        "md": md_path,
        "csv": csv_path,
        "tasks_in_scope": len(in_scope),
        "critical": len(critical),
        "prev_month_hours": format_hours(total_prev_month),
        "prev_month_label": pm_label,
    }
