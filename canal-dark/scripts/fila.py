"""Funções compartilhadas para ler/escrever data/fila_producao.json, usadas
por todos os scripts do pipeline."""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FILA_JSON = DATA_DIR / "fila_producao.json"


def carregar_fila() -> list[dict]:
    return json.loads(FILA_JSON.read_text(encoding="utf-8"))


def salvar_fila(fila: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILA_JSON.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
