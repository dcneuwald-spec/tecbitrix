"""
Testes das partes puras (sem navegador): parsing de datas/durações,
cálculo do mês anterior, tradução de status, guarda de tokens e relatório.

Rodar:  python -m pytest tests/  (ou  python tests/test_logica.py)
"""

import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitrix_readonly.guard import MUTATION_TOKENS, GuardLog, _tokenize
from bitrix_readonly.report import (
    build_report, previous_month_range, translate_status,
)
from bitrix_readonly.scraper import (
    Task, TimeEntry, format_hours, parse_date_pt, parse_duration_to_seconds,
)

TODAY = date(2026, 7, 4)


def test_parse_date_pt():
    assert parse_date_pt("31/12/2025") == date(2025, 12, 31)
    assert parse_date_pt("05.03.26") == date(2026, 3, 5)
    assert parse_date_pt("12 de janeiro de 2026") == date(2026, 1, 12)
    assert parse_date_pt("12 jun", TODAY) == date(2026, 6, 12)
    assert parse_date_pt("hoje", TODAY) == TODAY
    assert parse_date_pt("ontem", TODAY) == date(2026, 7, 3)
    assert parse_date_pt("texto sem data") is None


def test_parse_duration():
    assert parse_duration_to_seconds("01:30:00") == 5400
    assert parse_duration_to_seconds("1:30") == 5400
    assert parse_duration_to_seconds("1h 30min") == 5400
    assert parse_duration_to_seconds("90 min") == 5400
    assert parse_duration_to_seconds("2 h") == 7200
    assert parse_duration_to_seconds("sem tempo") is None
    assert format_hours(5400) == "1:30"


def test_previous_month_range():
    assert previous_month_range(TODAY) == (date(2026, 6, 1), date(2026, 6, 30))
    assert previous_month_range(date(2026, 1, 15)) == (
        date(2025, 12, 1), date(2025, 12, 31)
    )


def test_guard_tokens():
    # leitura passa
    assert not set(_tokenize("tasks.task.list")) & MUTATION_TOKENS
    assert not set(_tokenize("mobile.tasks.getList")) & MUTATION_TOKENS
    # escrita é detectada
    assert "add" in set(_tokenize("tasks.task.add"))
    assert "complete" in set(_tokenize("tasks.task.complete"))
    assert "set" in set(_tokenize("main.pageOption.set"))
    assert "add" in set(_tokenize("tasks.task.elapsedItem.Add"))


def test_translate_status():
    atrasada = Task(task_id="1", status="Em andamento", deadline=date(2026, 6, 1))
    assert translate_status(atrasada, TODAY) == "Em andamento (atrasada)"
    concluida = Task(task_id="2", status="concluida", closed=date(2026, 6, 2))
    assert translate_status(concluida, TODAY) == "Concluída"
    pendente_en = Task(task_id="3", status="Pending")
    assert translate_status(pendente_en, TODAY) == "Aguardando ação"


def test_hours_and_report():
    import config

    andamento = Task(task_id="4", title="Ativa", status="Em andamento",
                     created=date(2026, 2, 1))
    andamento.time_entries = [
        TimeEntry(date(2026, 6, 10), "Ana", 3600),
        TimeEntry(date(2026, 5, 10), "Ana", 7200),
    ]
    assert andamento.total_seconds == 10800
    assert andamento.seconds_in_period(date(2026, 6, 1), date(2026, 6, 30)) == 3600

    parada = Task(task_id="5", title="Parada", status="Nova",
                  created=date(2026, 3, 1))
    antiga = Task(task_id="6", title="Antiga", status="Em andamento",
                  created=date(2025, 5, 1))

    with tempfile.TemporaryDirectory() as tmp:
        original = config.OUTPUT_DIR
        config.OUTPUT_DIR = tmp
        try:
            res = build_report([andamento, parada, antiga], GuardLog(), TODAY)
        finally:
            config.OUTPUT_DIR = original

        assert res["tasks_in_scope"] == 2      # 'Antiga' (2025) fora do recorte
        assert res["critical"] == 1            # 'Parada': Nova + 0 horas
        assert res["prev_month_hours"] == "1:00"
        assert os.path.basename(res["md"]).startswith("relatorio_")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✓ {name}")
    print("Todos os testes passaram.")
