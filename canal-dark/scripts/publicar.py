"""Prepara os arquivos de cada vídeo pronto para publicação MANUAL no TikTok.

O TikTok não oferece uma forma simples de publicação automática sem que o app
seja previamente aprovado pela Content Posting API oficial, então este script
apenas organiza tudo para você subir manualmente pelo app.

Para cada item da fila com status "thumbnail_pronta", cria uma pasta em
data/publicacoes/<video_id>/ com:
    - legenda.txt   → legenda + hashtags prontos para colar no TikTok
    - video.mp4     → cópia do vídeo, se item["video_path"] existir
    - capa.jpg      → cópia da capa, se item["thumbnail_path"] existir
    - LEIA-ME.txt   → checklist do que falta e como publicar

Depois de publicar manualmente, marque o item como concluído:
    python scripts/publicar.py --marcar-publicado <video_id>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILA_JSON = DATA_DIR / "fila_producao.json"
PUBLICACOES_DIR = DATA_DIR / "publicacoes"

LIMITE_LEGENDA_TIKTOK = 2200


def carregar_fila() -> list[dict]:
    return json.loads(FILA_JSON.read_text(encoding="utf-8"))


def salvar_fila(fila: list[dict]) -> None:
    FILA_JSON.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")


def montar_legenda(item: dict) -> str:
    hashtags = " ".join(f"#{h}" for h in item.get("hashtags", []))
    legenda = f"{item.get('legenda', '').strip()}\n\n{hashtags}".strip()
    if len(legenda) > LIMITE_LEGENDA_TIKTOK:
        print(
            f"  Aviso: legenda de {item['video_id']} passa do limite do TikTok "
            f"({len(legenda)}/{LIMITE_LEGENDA_TIKTOK} caracteres).",
            file=sys.stderr,
        )
    return legenda


def preparar_pacote(item: dict) -> None:
    pasta = PUBLICACOES_DIR / item["video_id"]
    pasta.mkdir(parents=True, exist_ok=True)

    (pasta / "legenda.txt").write_text(montar_legenda(item), encoding="utf-8")

    pendencias = []
    for chave, script_responsavel, nome_destino in (
        ("video_path", "montar_video.py", "video.mp4"),
        ("thumbnail_path", "gerar_thumbnail.py", "capa.jpg"),
    ):
        origem = item.get(chave)
        if origem and Path(origem).exists():
            shutil.copy2(origem, pasta / nome_destino)
        else:
            pendencias.append((chave, script_responsavel))

    linhas = [
        f"Título sugerido: {item.get('titulo_sugerido', '')}",
        "",
        "Checklist para publicar manualmente no TikTok:",
        "1. Abra o app do TikTok e crie uma nova publicação.",
    ]
    if any(chave == "video_path" for chave, _ in pendencias):
        linhas.append("2. Envie o vídeo — AINDA NÃO GERADO (rode montar_video.py).")
    else:
        linhas.append("2. Envie o vídeo (veja video.mp4 nesta pasta).")
    if any(chave == "thumbnail_path" for chave, _ in pendencias):
        linhas.append("3. Defina a capa — AINDA NÃO GERADA (rode gerar_thumbnail.py).")
    else:
        linhas.append("3. Defina a capa (veja capa.jpg nesta pasta).")
    linhas += [
        "4. Cole o conteúdo de legenda.txt no campo de legenda.",
        "5. Publique e depois rode:",
        f"   python scripts/publicar.py --marcar-publicado {item['video_id']}",
    ]
    (pasta / "LEIA-ME.txt").write_text("\n".join(linhas), encoding="utf-8")

    if pendencias:
        faltando = ", ".join(chave for chave, _ in pendencias)
        print(f"  {item['video_id']}: pacote criado com pendências ({faltando}) em {pasta}")
    else:
        print(f"  {item['video_id']}: pacote completo em {pasta}")


def marcar_publicado(video_id: str) -> None:
    fila = carregar_fila()
    for item in fila:
        if item["video_id"] == video_id:
            item["status"] = "publicado"
            salvar_fila(fila)
            print(f"{video_id} marcado como publicado.")
            return
    print(f"video_id '{video_id}' não encontrado em {FILA_JSON}.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--marcar-publicado",
        metavar="VIDEO_ID",
        help="Marca um item como publicado após o upload manual no TikTok.",
    )
    args = parser.parse_args()

    if args.marcar_publicado:
        marcar_publicado(args.marcar_publicado)
        return

    fila = carregar_fila()
    pendentes = [item for item in fila if item["status"] == "thumbnail_pronta"]
    if not pendentes:
        print("Nenhum item com status 'thumbnail_pronta' aguardando publicação.")
        return

    PUBLICACOES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Preparando {len(pendentes)} pacote(s) para upload manual em {PUBLICACOES_DIR}...")
    for item in pendentes:
        preparar_pacote(item)

    for item in pendentes:
        item["status"] = "pronto_para_upload_manual"
    salvar_fila(fila)


if __name__ == "__main__":
    main()
