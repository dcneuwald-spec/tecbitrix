"""Utilitário de imagem compartilhado entre gerar_thumbnail.py e montar_video.py."""

from __future__ import annotations

import numpy as np
from PIL import Image


def criar_fundo_gradiente(
    largura: int, altura: int, cor_topo: tuple[int, int, int], cor_base: tuple[int, int, int]
) -> Image.Image:
    """Cria um fundo em gradiente vertical entre duas cores RGB."""
    topo = np.array(cor_topo, dtype=float)
    base = np.array(cor_base, dtype=float)
    t = np.linspace(0, 1, altura).reshape(altura, 1)
    coluna = (topo * (1 - t) + base * t).astype("uint8")
    gradiente = np.repeat(coluna[:, None, :], largura, axis=1)
    return Image.fromarray(gradiente)
