"""Gera a narração em áudio (TTS) para os roteiros prontos em data/fila_producao.json,
usando a API da ElevenLabs (vozes naturais em português).

As sugestões de texto na tela do roteiro (ex.: "[Mostrar copo de água]") são
removidas antes da narração — elas são só indicações visuais para o editor de
vídeo, não devem ser faladas.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from fila import DATA_DIR, carregar_fila, salvar_fila

load_dotenv()

AUDIO_DIR = DATA_DIR / "audio"

# Voz multilíngue padrão da ElevenLabs ("Rachel") — troque por ELEVENLABS_VOICE_ID
# no .env para usar outra voz da sua conta (ex.: uma voz brasileira específica).
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

TEXTO_NA_TELA_RE = re.compile(r"\[[^\]]*\]")


def limpar_texto_para_narracao(roteiro: str) -> str:
    """Remove as sugestões de texto na tela (entre colchetes) do roteiro,
    deixando só o que deve ser narrado em voz alta."""
    sem_colchetes = TEXTO_NA_TELA_RE.sub("", roteiro)
    linhas = [linha.strip() for linha in sem_colchetes.splitlines()]
    return "\n".join(linha for linha in linhas if linha)


def gerar_audio(client: ElevenLabs, texto: str, destino: Path) -> None:
    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=texto,
        model_id=MODEL_ID,
        output_format="mp3_44100_128",
    )
    with destino.open("wb") as f:
        for chunk in audio:
            f.write(chunk)


def main() -> None:
    fila = carregar_fila()
    pendentes = [item for item in fila if item["status"] == "roteiro_pronto"]
    if not pendentes:
        print("Nenhum roteiro com status 'roteiro_pronto' aguardando voz.")
        return

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    for i, item in enumerate(pendentes, start=1):
        print(f"[{i}/{len(pendentes)}] Gerando voz para: {item['titulo_sugerido']}")
        texto = limpar_texto_para_narracao(item["roteiro"])
        if not texto:
            print(f"  Roteiro de {item['video_id']} ficou vazio após limpeza — pulando.", file=sys.stderr)
            continue

        destino = AUDIO_DIR / f"{item['video_id']}.mp3"
        try:
            gerar_audio(client, texto, destino)
        except ApiError as e:
            print(f"  Falhou ao gerar voz para {item['video_id']}: {e}", file=sys.stderr)
            continue

        item["audio_path"] = str(destino)
        item["status"] = "voz_pronta"
        print(f"  Áudio salvo em {destino}")

    salvar_fila(fila)


if __name__ == "__main__":
    main()
