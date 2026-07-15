"""Coleta vídeos em alta no YouTube, salva em data/ideias.csv e gera roteiros
(roteiro + descrição + hashtags) para cada ideia usando a API da Anthropic,
salvando o resultado estruturado em data/fila_producao.json.

Uso:
    python scripts/gerar_roteiro.py              # busca trends + gera roteiros
    python scripts/gerar_roteiro.py --so-roteiros # usa o ideias.csv existente,
                                                    sem buscar trends de novo
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IDEIAS_CSV = DATA_DIR / "ideias.csv"
FILA_JSON = DATA_DIR / "fila_producao.json"

REGION_CODE = os.environ.get("YOUTUBE_REGION_CODE", "BR")
CATEGORY_ID = os.environ.get("YOUTUBE_CATEGORY_ID")  # ex.: "24" (Entretenimento)
MAX_RESULTS = int(os.environ.get("YOUTUBE_MAX_RESULTS", "25"))

CSV_FIELDS = [
    "video_id",
    "titulo",
    "canal",
    "categoria_id",
    "visualizacoes",
    "likes",
    "comentarios",
    "url",
    "coletado_em",
]


class Roteiro(BaseModel):
    titulo_sugerido: str
    roteiro: str
    descricao: str
    hashtags: list[str]


def buscar_trends_youtube() -> list[dict]:
    """Busca os vídeos em alta no YouTube (Data API v3) e salva em data/ideias.csv."""
    api_key = os.environ["YOUTUBE_API_KEY"]
    youtube = build("youtube", "v3", developerKey=api_key)

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": REGION_CODE,
        "maxResults": MAX_RESULTS,
    }
    if CATEGORY_ID:
        params["videoCategoryId"] = CATEGORY_ID

    try:
        response = youtube.videos().list(**params).execute()
    except HttpError as e:
        print(f"Erro ao consultar a YouTube Data API: {e}", file=sys.stderr)
        raise

    coletado_em = datetime.now(timezone.utc).isoformat()
    ideias = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        ideias.append(
            {
                "video_id": item["id"],
                "titulo": snippet["title"],
                "canal": snippet["channelTitle"],
                "categoria_id": snippet.get("categoryId", ""),
                "visualizacoes": stats.get("viewCount", "0"),
                "likes": stats.get("likeCount", "0"),
                "comentarios": stats.get("commentCount", "0"),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "coletado_em": coletado_em,
            }
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with IDEIAS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(ideias)

    print(f"{len(ideias)} ideias salvas em {IDEIAS_CSV}")
    return ideias


def ler_ideias_csv() -> list[dict]:
    with IDEIAS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


PROMPT_TEMPLATE = """Você é um roteirista especialista em vídeos de YouTube para um canal \
de histórias sombrias (true crime, mistérios e curiosidades dark).

Com base na ideia/tendência de referência abaixo, crie:
1. Um título otimizado para YouTube (chamativo, sem clickbait enganoso)
2. Um roteiro completo de narração (gancho nos primeiros 15 segundos, desenvolvimento \
em blocos e conclusão com chamada para se inscrever no canal)
3. Uma descrição otimizada para SEO (2 a 3 parágrafos)
4. Uma lista de 8 a 12 hashtags relevantes (sem o caractere #)

Ideia/tendência de referência:
Título original: {titulo}
Canal: {canal}
Visualizações: {visualizacoes}

Responda em português do Brasil, apenas com o conteúdo solicitado."""


def gerar_roteiro_com_claude(client: anthropic.Anthropic, ideia: dict) -> Roteiro:
    prompt = PROMPT_TEMPLATE.format(
        titulo=ideia["titulo"],
        canal=ideia["canal"],
        visualizacoes=ideia.get("visualizacoes", "N/A"),
    )
    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
        output_format=Roteiro,
    )
    return response.parsed_output


def gerar_fila_producao(ideias: list[dict]) -> None:
    client = anthropic.Anthropic()
    fila = []
    for i, ideia in enumerate(ideias, start=1):
        print(f"[{i}/{len(ideias)}] Gerando roteiro para: {ideia['titulo']}")
        try:
            roteiro = gerar_roteiro_com_claude(client, ideia)
        except anthropic.APIError as e:
            print(f"  Falhou ao gerar roteiro para {ideia['video_id']}: {e}", file=sys.stderr)
            continue

        fila.append(
            {
                "video_id": ideia["video_id"],
                "titulo_original": ideia["titulo"],
                "url_referencia": ideia["url"],
                "titulo_sugerido": roteiro.titulo_sugerido,
                "roteiro": roteiro.roteiro,
                "descricao": roteiro.descricao,
                "hashtags": roteiro.hashtags,
                "status": "roteiro_pronto",
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            }
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FILA_JSON.open("w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)

    print(f"{len(fila)} roteiros salvos em {FILA_JSON}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--so-roteiros",
        action="store_true",
        help="Pula a busca de trends e usa o data/ideias.csv já existente.",
    )
    args = parser.parse_args()

    if args.so_roteiros:
        if not IDEIAS_CSV.exists():
            print(f"{IDEIAS_CSV} não existe. Rode sem --so-roteiros primeiro.", file=sys.stderr)
            sys.exit(1)
        ideias = ler_ideias_csv()
    else:
        ideias = buscar_trends_youtube()

    if not ideias:
        print("Nenhuma ideia encontrada.")
        sys.exit(0)

    gerar_fila_producao(ideias)


if __name__ == "__main__":
    main()
