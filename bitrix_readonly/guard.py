"""
Guarda de segurança SOMENTE LEITURA.

Duas camadas de proteção, ambas ativas durante toda a extração:

1. GUARDA DE REDE (install_network_guard)
   Intercepta todas as requisições do navegador e BLOQUEIA qualquer chamada
   ajax do Bitrix24 cuja "action" contenha um verbo de mutação (add, update,
   delete, complete, set, save...). Também bloqueia métodos HTTP PUT/PATCH/
   DELETE. Requisições bloqueadas são registradas para constar no relatório
   final. Como o script nunca deveria disparar escrita, qualquer bloqueio
   indica um clique/fluxo inesperado — e o dado NÃO chega ao servidor.

2. CLIQUE SEGURO (safe_click / assert_element_readonly)
   Antes de qualquer clique, o texto/aria-label/title do elemento é comparado
   com uma lista de palavras proibidas (salvar, editar, concluir, excluir...).
   Se houver correspondência, o clique NÃO é executado e uma exceção
   ReadOnlyViolation é lançada, interrompendo o fluxo para reportar ao usuário.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, urlparse


class ReadOnlyViolation(RuntimeError):
    """Lançada quando uma ação potencialmente de escrita seria executada."""


@dataclass
class GuardLog:
    """Registro de eventos da guarda (bloqueios e avisos)."""

    blocked_requests: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def block(self, detail: str) -> None:
        entry = f"[{datetime.now():%H:%M:%S}] BLOQUEADO: {detail}"
        self.blocked_requests.append(entry)
        print(f"  🔒 {entry}")

    def warn(self, detail: str) -> None:
        entry = f"[{datetime.now():%H:%M:%S}] AVISO: {detail}"
        self.warnings.append(entry)
        print(f"  ⚠️  {entry}")


# Tokens de mutação: se aparecerem como palavra isolada na "action" de uma
# chamada ajax do Bitrix, a requisição é bloqueada. A comparação é feita por
# token (camelCase e pontos são separados), evitando falsos positivos como
# "dataset" conter "set".
MUTATION_TOKENS = {
    "add", "update", "delete", "remove", "complete", "renew", "defer",
    "start", "pause", "stop", "approve", "disapprove", "set", "save",
    "create", "edit", "move", "delegate", "mute", "unmute", "follow",
    "unfollow", "upload", "write", "finish", "close", "reopen", "restore",
    "attach", "detach", "bind", "unbind", "invite", "join", "leave",
    "accept", "decline", "assign", "change", "ping", "watch", "unwatch",
}

# Métodos HTTP que nunca são necessários para leitura no Bitrix24 web
FORBIDDEN_HTTP_METHODS = {"PUT", "PATCH", "DELETE"}

# Palavras proibidas em elementos clicáveis (PT/EN, com e sem acento).
# Comparadas por palavra inteira, sem diferenciar maiúsculas.
FORBIDDEN_CLICK_WORDS = {
    # português
    "salvar", "gravar", "editar", "edição", "edicao", "excluir", "apagar",
    "remover", "deletar", "concluir", "finalizar", "encerrar", "aprovar",
    "reprovar", "criar", "adicionar", "novo", "nova", "iniciar", "pausar",
    "retomar", "reabrir", "renovar", "adiar", "mover", "delegar", "atribuir",
    "responder", "comentar", "enviar", "anexar", "carregar", "importar",
    "convidar", "aplicar", "confirmar", "alterar", "modificar", "atualizar",
    # inglês (a interface pode estar parcialmente em EN)
    "save", "edit", "delete", "remove", "complete", "finish", "approve",
    "create", "add", "new", "start", "pause", "resume", "reopen", "renew",
    "defer", "move", "delegate", "assign", "reply", "comment", "send",
    "submit", "attach", "upload", "import", "invite", "apply", "update",
}

# Exceções explícitas: rótulos que contêm palavra proibida mas são
# comprovadamente de navegação/leitura (comparação pelo rótulo completo
# normalizado). Ex.: nenhum por padrão — adicionar aqui somente após revisão.
ALLOWED_CLICK_LABELS: set[str] = set()


def _tokenize(text: str) -> list[str]:
    """Separa camelCase, pontos e não-letras em tokens minúsculos."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    return [t for t in re.split(r"[^a-zA-Z]+", text.lower()) if t]


def _action_from_url(url: str) -> str | None:
    try:
        qs = parse_qs(urlparse(url).query)
        return (qs.get("action") or [None])[0]
    except Exception:
        return None


def install_network_guard(context, log: GuardLog) -> None:
    """
    Instala a interceptação de rede no BrowserContext.

    Bloqueia (route.abort) toda requisição classificada como mutação e
    registra o bloqueio no GuardLog. Requisições de leitura seguem normalmente.
    """

    def handler(route):
        request = route.request
        url = request.url
        method = request.method.upper()

        if method in FORBIDDEN_HTTP_METHODS:
            log.block(f"método HTTP {method} em {url[:160]}")
            route.abort()
            return

        action = _action_from_url(url)
        if action is None and method == "POST":
            # Bitrix também envia a action no corpo em alguns fluxos legados
            try:
                body = request.post_data or ""
                m = re.search(r"(?:^|&)action=([^&]+)", body)
                if m:
                    action = m.group(1)
            except Exception:
                action = None

        if action:
            tokens = set(_tokenize(action))
            hit = tokens & MUTATION_TOKENS
            if hit:
                log.block(
                    f"ação ajax de escrita '{action}' "
                    f"(tokens: {', '.join(sorted(hit))}) em {url[:160]}"
                )
                route.abort()
                return

        route.continue_()

    # Toda a superfície ajax do Bitrix passa pela guarda
    context.route("**/bitrix/services/main/ajax.php*", handler)
    context.route("**/bitrix/components/**/ajax.php*", handler)
    context.route("**/bitrix/tools/**", handler)
    context.route("**/rest/**", handler)  # nenhuma chamada REST deve ocorrer


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def describe_element(locator) -> str:
    """Texto legível do elemento para logs e verificação."""
    parts = []
    for getter in (
        lambda: locator.inner_text(timeout=2000),
        lambda: locator.get_attribute("aria-label", timeout=2000),
        lambda: locator.get_attribute("title", timeout=2000),
        lambda: locator.get_attribute("value", timeout=2000),
    ):
        try:
            v = getter()
            if v:
                parts.append(v)
        except Exception:
            pass
    return " | ".join(parts)


def assert_element_readonly(locator, purpose: str) -> None:
    """
    Verifica que o elemento a ser clicado não representa uma ação de escrita.
    Lança ReadOnlyViolation em caso de correspondência com palavra proibida.
    """
    label = describe_element(locator)
    normalized = _normalize(label)

    if normalized in ALLOWED_CLICK_LABELS:
        return

    words = set(re.split(r"[^\wÀ-ÿ]+", normalized))
    hit = words & FORBIDDEN_CLICK_WORDS
    if hit:
        raise ReadOnlyViolation(
            f"Clique abortado ({purpose}): o elemento '{label[:120]}' contém "
            f"palavra(s) de ação de escrita: {', '.join(sorted(hit))}. "
            "Nenhuma alteração foi feita. Revise o fluxo antes de prosseguir."
        )


def safe_click(locator, purpose: str, log: GuardLog | None = None) -> None:
    """Clica somente após validar que o elemento é de navegação/leitura."""
    assert_element_readonly(locator, purpose)
    if log:
        print(f"  👆 clique de leitura: {purpose}")
    locator.click()
