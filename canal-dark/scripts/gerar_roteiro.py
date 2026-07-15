"""Busca vídeos em alta no YouTube sobre nutrição/dieta/emagrecimento/receitas
(como proxy de tendência, já que o TikTok não expõe uma API pública de
trends), salva em data/ideias.csv e gera roteiros originais para TikTok
(roteiro + legenda + hashtags) para cada ideia usando a API da Anthropic,
salvando o resultado estruturado em data/fila_producao.json.

Uso:
    python scripts/gerar_roteiro.py              # busca trends + gera roteiros
    python scripts/gerar_roteiro.py --so-roteiros # usa o ideias.csv existente,
                                                    sem buscar trends de novo
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Iterator

import anthropic
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

from fila import DATA_DIR, salvar_fila

load_dotenv()

IDEIAS_CSV = DATA_DIR / "ideias.csv"

REGION_CODE = os.environ.get("YOUTUBE_REGION_CODE", "BR")

# Termos usados para localizar vídeos em alta no nicho (o YouTube não tem uma
# categoria própria de "nutrição/dieta", então buscamos por palavra-chave).
DEFAULT_TERMOS = (
    "receita fit,dieta cetogênica,emagrecimento,receita saudável,nutrição,"
    "low carb,perder peso rápido,jejum intermitente,dieta para emagrecer,"
    "receita de dieta"
)
TERMOS_BUSCA = [
    t.strip()
    for t in os.environ.get("NICHO_TERMOS_BUSCA", DEFAULT_TERMOS).split(",")
    if t.strip()
]
RESULTADOS_POR_TERMO = int(os.environ.get("YOUTUBE_RESULTADOS_POR_TERMO", "5"))
DIAS_RECENCIA = int(os.environ.get("YOUTUBE_DIAS_RECENCIA", "30"))
MAX_RESULTS = int(os.environ.get("YOUTUBE_MAX_RESULTS", "25"))

CSV_FIELDS = [
    "video_id",
    "titulo",
    "canal",
    "termo_busca",
    "visualizacoes",
    "likes",
    "comentarios",
    "url",
    "coletado_em",
]


class RoteiroTikTok(BaseModel):
    titulo_sugerido: str
    roteiro: str
    legenda: str
    hashtags: list[str]


def _em_lotes(itens: list[str], tamanho: int) -> Iterator[list[str]]:
    for i in range(0, len(itens), tamanho):
        yield itens[i : i + tamanho]


def buscar_trends_youtube() -> list[dict]:
    """Busca vídeos em alta no nicho de nutrição/dieta (YouTube Data API v3,
    usado como proxy de tendência) e salva em data/ideias.csv."""
    api_key = os.environ["YOUTUBE_API_KEY"]
    youtube = build("youtube", "v3", developerKey=api_key)
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=DIAS_RECENCIA)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    termo_por_video_id: dict[str, str] = {}
    for termo in TERMOS_BUSCA:
        try:
            resp = (
                youtube.search()
                .list(
                    part="id",
                    q=termo,
                    type="video",
                    order="viewCount",
                    maxResults=RESULTADOS_POR_TERMO,
                    regionCode=REGION_CODE,
                    relevanceLanguage="pt",
                    publishedAfter=published_after,
                )
                .execute()
            )
        except HttpError as e:
            print(f"Erro ao buscar '{termo}': {e}", file=sys.stderr)
            continue

        for item in resp.get("items", []):
            video_id = item["id"]["videoId"]
            termo_por_video_id.setdefault(video_id, termo)

    if not termo_por_video_id:
        print("Nenhum vídeo encontrado para os termos configurados.")
        return []

    coletado_em = datetime.now(timezone.utc).isoformat()
    ideias = []
    for lote in _em_lotes(list(termo_por_video_id), 50):  # limite da API por chamada
        try:
            resp = (
                youtube.videos()
                .list(part="snippet,statistics", id=",".join(lote))
                .execute()
            )
        except HttpError as e:
            print(f"Erro ao consultar detalhes dos vídeos: {e}", file=sys.stderr)
            continue

        for item in resp.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            ideias.append(
                {
                    "video_id": item["id"],
                    "titulo": snippet["title"],
                    "canal": snippet["channelTitle"],
                    "termo_busca": termo_por_video_id.get(item["id"], ""),
                    "visualizacoes": stats.get("viewCount", "0"),
                    "likes": stats.get("likeCount", "0"),
                    "comentarios": stats.get("commentCount", "0"),
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "coletado_em": coletado_em,
                }
            )

    ideias.sort(key=lambda x: int(x["visualizacoes"] or 0), reverse=True)
    ideias = ideias[:MAX_RESULTS]

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


PROMPT_TEMPLATE = """Você é um roteirista especialista em vídeos curtos de TikTok para um \
canal de nutrição, emagrecimento, dietas e receitas saudáveis.

Com base no vídeo de referência abaixo (usado apenas como indicação de assunto em alta \
no nicho — NÃO copie o conteúdo dele), crie um vídeo ORIGINAL para TikTok com:

1. Um título/gancho de capa (curto, chamativo, para o texto de capa ou os primeiros \
segundos na tela)
2. Um roteiro de narração para vídeo vertical de 30 a 90 segundos: gancho nos primeiros \
2-3 segundos, conteúdo direto (ex.: passo a passo de uma receita, ou uma dica prática de \
emagrecimento/nutrição) e um call-to-action final para seguir o perfil. Quando fizer \
sentido, indique sugestões de texto na tela entre colchetes contendo APENAS o texto que \
deve aparecer na tela, sem prefixos como "Texto na tela:" ou "Mostrar:" — \
ex.: [3 dicas pra emagrecer sem passar fome], não [Texto na tela: 3 dicas pra emagrecer].
3. Uma legenda para a publicação no TikTok (curta, com emojis moderados, terminando com \
uma pergunta ou chamada para comentar)
4. Uma lista de 6 a 10 hashtags relevantes para o nicho (sem o caractere #), misturando \
hashtags amplas (ex.: emagrecimento, dieta, receitafit) com outras mais específicas ao \
tema do vídeo

Regras importantes de conteúdo:
- Não prometa emagrecimento milagroso, resultados garantidos ou "cura" de doenças.
- Não invente números específicos (calorias, macros, prazos) que não estejam no vídeo de \
referência; se citar números, deixe claro que são aproximados.
- Ao dar recomendações de dieta, inclua uma frase breve lembrando que isso não substitui \
orientação de um nutricionista ou médico.

Vídeo de referência (apenas contexto de tendência do nicho, não copie o conteúdo):
Título original: {titulo}
Canal: {canal}
Visualizações: {visualizacoes}

Responda em português do Brasil, apenas com o conteúdo solicitado."""


def gerar_roteiro_com_claude(client: anthropic.Anthropic, ideia: dict) -> RoteiroTikTok:
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
        output_format=RoteiroTikTok,
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
                "plataforma": "tiktok",
                "titulo_sugerido": roteiro.titulo_sugerido,
                "roteiro": roteiro.roteiro,
                "legenda": roteiro.legenda,
                "hashtags": roteiro.hashtags,
                "status": "roteiro_pronto",
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            }
        )

    salvar_fila(fila)
    print(f"{len(fila)} roteiros salvos em {DATA_DIR / 'fila_producao.json'}")


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
