"""Monta o vídeo final (narração + imagens/clipes + legendas) para os itens
da fila com status "voz_pronta".

Ainda não implementado — próximo passo do pipeline após gerar_voz.py.
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
    pendentes = [item for item in fila if item["status"] == "voz_pronta"]
    print(f"{len(pendentes)} item(ns) aguardando montagem de vídeo.")
    # TODO: montar o vídeo (ex.: moviepy/ffmpeg), salvar o arquivo gerado e
    # atualizar item["status"] = "video_pronto".


if __name__ == "__main__":
    main()
