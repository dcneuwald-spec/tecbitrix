"""Publica no YouTube os itens da fila com status "thumbnail_pronta"
(upload do vídeo, thumbnail, título, descrição e hashtags via YouTube Data API).

Ainda não implementado — passo final do pipeline após gerar_thumbnail.py.
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
    pendentes = [item for item in fila if item["status"] == "thumbnail_pronta"]
    print(f"{len(pendentes)} item(ns) prontos para publicação.")
    # TODO: autenticar via OAuth (youtube.upload scope), enviar o vídeo com
    # youtube.videos().insert(...), enviar a thumbnail e atualizar
    # item["status"] = "publicado".


if __name__ == "__main__":
    main()
