"""Gera a capa (cover) do vídeo para os itens da fila com status "video_pronto",
no formato vertical 1080x1920 usado pelo TikTok: fundo em gradiente + título
sugerido centralizado.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import ImageDraw, ImageFont

from fila import DATA_DIR, carregar_fila, salvar_fila
from imagem_utils import criar_fundo_gradiente

BASE_DIR = Path(__file__).resolve().parent.parent
CAPAS_DIR = DATA_DIR / "capas"
FONTE_BOLD = BASE_DIR / "assets" / "fonts" / "DejaVuSans-Bold.ttf"

LARGURA, ALTURA = 1080, 1920

# Gradiente com tema de saúde/nutrição (verde escuro -> verde claro).
# Troque essas cores para adaptar à identidade visual do canal.
COR_TOPO = (10, 61, 41)
COR_BASE = (64, 145, 108)
COR_TEXTO = (255, 255, 255)
COR_SOMBRA = (0, 0, 0)


def quebrar_linhas(draw: ImageDraw.ImageDraw, texto: str, fonte: ImageFont.FreeTypeFont, largura_max: int) -> list[str]:
    linhas: list[str] = []
    for paragrafo in textwrap.wrap(texto, width=40, break_long_words=False):
        linhas.append(paragrafo)

    # Reajusta linhas muito largas medindo em pixels (o wrap acima é só uma
    # estimativa por número de caracteres).
    linhas_ajustadas: list[str] = []
    for linha in linhas:
        palavras = linha.split()
        atual = ""
        for palavra in palavras:
            candidato = f"{atual} {palavra}".strip()
            if draw.textlength(candidato, font=fonte) <= largura_max:
                atual = candidato
            else:
                if atual:
                    linhas_ajustadas.append(atual)
                atual = palavra
        if atual:
            linhas_ajustadas.append(atual)
    return linhas_ajustadas


def gerar_capa(titulo: str, destino: Path) -> None:
    imagem = criar_fundo_gradiente(LARGURA, ALTURA, COR_TOPO, COR_BASE)
    draw = ImageDraw.Draw(imagem)

    tamanho_fonte = 88
    fonte = ImageFont.truetype(str(FONTE_BOLD), tamanho_fonte)
    margem = 90
    largura_max = LARGURA - 2 * margem

    linhas = quebrar_linhas(draw, titulo.upper(), fonte, largura_max)

    altura_linha = tamanho_fonte + 20
    altura_bloco = altura_linha * len(linhas)
    y = (ALTURA - altura_bloco) / 2

    for linha in linhas:
        largura_linha = draw.textlength(linha, font=fonte)
        x = (LARGURA - largura_linha) / 2
        # Contorno/sombra para legibilidade sobre o fundo.
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            draw.text((x + dx, y + dy), linha, font=fonte, fill=COR_SOMBRA)
        draw.text((x, y), linha, font=fonte, fill=COR_TEXTO)
        y += altura_linha

    destino.parent.mkdir(parents=True, exist_ok=True)
    imagem.convert("RGB").save(destino, "JPEG", quality=90)


def main() -> None:
    fila = carregar_fila()
    pendentes = [item for item in fila if item["status"] == "video_pronto"]
    if not pendentes:
        print("Nenhum item com status 'video_pronto' aguardando capa.")
        return

    CAPAS_DIR.mkdir(parents=True, exist_ok=True)
    for i, item in enumerate(pendentes, start=1):
        print(f"[{i}/{len(pendentes)}] Gerando capa para: {item['titulo_sugerido']}")
        destino = CAPAS_DIR / f"{item['video_id']}.jpg"
        gerar_capa(item["titulo_sugerido"], destino)
        item["thumbnail_path"] = str(destino)
        item["status"] = "thumbnail_pronta"
        print(f"  Capa salva em {destino}")

    salvar_fila(fila)


if __name__ == "__main__":
    main()
