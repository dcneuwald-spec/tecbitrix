"""Monta o vídeo final vertical (1080x1920, formato TikTok) — narração +
fundo (imagens/clipes de assets/backgrounds/, ou gradiente gerado) + legendas
na tela — para os itens da fila com status "voz_pronta".

Para usar suas próprias imagens/clipes de fundo, coloque arquivos .jpg/.png/
.mp4/.mov em assets/backgrounds/ — eles são escolhidos ciclicamente a cada
vídeo. Sem nada nessa pasta, um fundo em gradiente é gerado automaticamente
(igual ao usado por gerar_thumbnail.py).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

from fila import DATA_DIR, carregar_fila, salvar_fila
from imagem_utils import criar_fundo_gradiente

BASE_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR = DATA_DIR / "videos"
BACKGROUNDS_DIR = BASE_DIR / "assets" / "backgrounds"
FONTE_BOLD = BASE_DIR / "assets" / "fonts" / "DejaVuSans-Bold.ttf"

LARGURA, ALTURA = 1080, 1920
FPS = 30

# Mesmo gradiente usado em gerar_thumbnail.py, para manter a identidade visual
# quando não há imagens/clipes de fundo em assets/backgrounds/.
COR_TOPO = (10, 61, 41)
COR_BASE = (64, 145, 108)

EXTENSOES_IMAGEM = (".jpg", ".jpeg", ".png")
EXTENSOES_VIDEO = (".mp4", ".mov")

TEXTO_NA_TELA_RE = re.compile(r"\[([^\]]*)\]")
PREFIXO_ROTULO_RE = re.compile(
    r"^(texto na tela|mostrar|on screen|tela)\s*[:\-]\s*", re.IGNORECASE
)


def extrair_legendas(roteiro: str) -> list[str]:
    """Usa as sugestões de texto na tela (entre colchetes) do roteiro como
    legendas, se houver; senão, quebra o texto narrado em frases curtas."""
    marcadas = [m.strip() for m in TEXTO_NA_TELA_RE.findall(roteiro) if m.strip()]
    if marcadas:
        # O prompt pede só o texto puro entre colchetes, mas o modelo às vezes
        # inclui um rótulo como "Texto na tela:" — removemos por segurança.
        return [PREFIXO_ROTULO_RE.sub("", m) for m in marcadas]

    sem_colchetes = TEXTO_NA_TELA_RE.sub("", roteiro).replace("\n", " ")
    frases = re.split(r"(?<=[.!?])\s+", sem_colchetes)
    return [f.strip() for f in frases if f.strip()]


def escolher_fundo(indice: int) -> Path | None:
    if not BACKGROUNDS_DIR.exists():
        return None
    arquivos = sorted(
        p
        for p in BACKGROUNDS_DIR.iterdir()
        if p.suffix.lower() in EXTENSOES_IMAGEM + EXTENSOES_VIDEO
    )
    if not arquivos:
        return None
    return arquivos[indice % len(arquivos)]


def _preencher_quadro(clip):
    """Redimensiona e corta o clipe para preencher o quadro vertical
    (comportamento tipo "object-fit: cover")."""
    clip = clip.resized(height=ALTURA)
    if clip.w < LARGURA:
        clip = clip.resized(width=LARGURA)
    return clip.cropped(x_center=clip.w / 2, y_center=clip.h / 2, width=LARGURA, height=ALTURA)


def clip_de_fundo(caminho: Path | None, duracao: float):
    if caminho is None:
        fundo = criar_fundo_gradiente(LARGURA, ALTURA, COR_TOPO, COR_BASE)
        return ImageClip(np.array(fundo)).with_duration(duracao)

    if caminho.suffix.lower() in EXTENSOES_VIDEO:
        clip = VideoFileClip(str(caminho)).without_audio()
        if clip.duration < duracao:
            repeticoes = int(duracao // clip.duration) + 1
            clip = concatenate_videoclips([clip] * repeticoes)
        clip = clip.subclipped(0, duracao)
    else:
        clip = ImageClip(str(caminho)).with_duration(duracao)

    return _preencher_quadro(clip)


def montar_legendas(legendas: list[str], duracao_total: float) -> list:
    if not legendas or duracao_total <= 0:
        return []

    pesos = [max(len(texto), 1) for texto in legendas]
    total_peso = sum(pesos)
    clipes = []
    t_atual = 0.0
    for texto, peso in zip(legendas, pesos):
        duracao = duracao_total * (peso / total_peso)
        legenda = (
            TextClip(
                font=str(FONTE_BOLD),
                text=texto,
                font_size=64,
                size=(LARGURA - 120, None),
                color="white",
                stroke_color="black",
                stroke_width=4,
                method="caption",
                text_align="center",
                horizontal_align="center",
            )
            .with_duration(duracao)
            .with_start(t_atual)
            .with_position(("center", int(ALTURA * 0.68)))
        )
        clipes.append(legenda)
        t_atual += duracao
    return clipes


def montar_video_item(item: dict, indice: int) -> Path:
    audio = AudioFileClip(item["audio_path"])
    duracao = audio.duration

    fundo = clip_de_fundo(escolher_fundo(indice), duracao)
    clipes_legenda = montar_legendas(extrair_legendas(item["roteiro"]), duracao)

    video = CompositeVideoClip([fundo, *clipes_legenda], size=(LARGURA, ALTURA)).with_audio(audio)

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    destino = VIDEOS_DIR / f"{item['video_id']}.mp4"
    video.write_videofile(
        str(destino), fps=FPS, codec="libx264", audio_codec="aac", logger=None
    )
    video.close()
    audio.close()
    return destino


def main() -> None:
    fila = carregar_fila()
    pendentes = [item for item in fila if item["status"] == "voz_pronta"]
    if not pendentes:
        print("Nenhum item com status 'voz_pronta' aguardando montagem de vídeo.")
        return

    for i, item in enumerate(pendentes):
        print(f"[{i + 1}/{len(pendentes)}] Montando vídeo para: {item['titulo_sugerido']}")
        try:
            destino = montar_video_item(item, i)
        except Exception as e:
            print(f"  Falhou ao montar vídeo para {item['video_id']}: {e}", file=sys.stderr)
            continue
        item["video_path"] = str(destino)
        item["status"] = "video_pronto"
        print(f"  Vídeo salvo em {destino}")

    salvar_fila(fila)


if __name__ == "__main__":
    main()
