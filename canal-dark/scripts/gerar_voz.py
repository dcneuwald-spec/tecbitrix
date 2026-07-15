"""Gera a narração em áudio (TTS) para os roteiros prontos em data/fila_producao.json.

Ainda não implementado — este é o próximo passo do pipeline após gerar_roteiro.py.
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
    pendentes = [item for item in fila if item["status"] == "roteiro_pronto"]
    print(f"{len(pendentes)} roteiro(s) aguardando geração de voz.")
    # TODO: integrar com uma API de TTS (ElevenLabs, Azure Speech, etc.),
    # salvar o áudio gerado e atualizar item["status"] = "voz_pronta".


if __name__ == "__main__":
    main()
