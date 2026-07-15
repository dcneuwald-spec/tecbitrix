"""Gera a thumbnail para os itens da fila com status "video_pronto".

Ainda não implementado — próximo passo do pipeline após montar_video.py.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILA_JSON = DATA_DIR / "fila_producao.json"


def carregar_fila() -> list[dict]:
    return json.loads(FILA_JSON.read_text(encoding="utf-8"))


def main() -> None:
    fila = carregar_fila()
    pendentes = [item for item in fila if item["status"] == "video_pronto"]
    print(f"{len(pendentes)} item(ns) aguardando geração de thumbnail.")
    # TODO: gerar a thumbnail (ex.: Pillow, ou uma API de geração de imagem),
    # salvar o arquivo gerado e atualizar item["status"] = "thumbnail_pronta".


if __name__ == "__main__":
    main()
