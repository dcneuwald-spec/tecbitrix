"""
Extração somente-leitura de dados de tarefas do Bitrix24 via Playwright.

Estratégia (100% leitura):
1. Localizar a EMPRESA do cliente no CRM pelo nome (ou usar COMPANY_ID fixo)
   e abrir a ficha dela (/crm/company/details/<ID>/). Alternativamente, o
   modo grupo/projeto continua disponível via --group-id.
2. Abrir a aba "Tarefas" da ficha da empresa (clique de leitura, validado
   pela guarda) e carregar todos os itens (rolagem + "mostrar mais").
3. Para cada tarefa, abrir a PÁGINA DE DETALHE por URL direta (navegação,
   não clique em botão de ação) e ler campos renderizados: título, status,
   responsável, datas, descrição, comentários e apontamentos de tempo.
4. Nenhum filtro é salvo no Bitrix: o recorte de período é aplicado
   localmente, em Python, sobre os dados extraídos.

A fragilidade natural de seletores em UI é mitigada com múltiplos fallbacks
e busca por rótulos de texto; tudo que não puder ser lido vira um AVISO no
relatório em vez de dado inventado.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

import config
from .guard import GuardLog, ReadOnlyViolation, safe_click


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------

@dataclass
class TimeEntry:
    """Um apontamento de horas dentro de uma tarefa."""
    entry_date: date | None
    person: str
    seconds: int
    comment: str = ""


@dataclass
class Task:
    task_id: str
    title: str = ""
    status: str = ""
    responsible: str = ""
    created: date | None = None
    deadline: date | None = None
    closed: date | None = None
    description: str = ""
    last_comments: list = field(default_factory=list)
    time_entries: list = field(default_factory=list)
    total_seconds_reported: int | None = None  # campo "Tempo gasto", se lido
    warnings: list = field(default_factory=list)
    url: str = ""

    @property
    def total_seconds(self) -> int:
        if self.time_entries:
            return sum(e.seconds for e in self.time_entries)
        return self.total_seconds_reported or 0

    def seconds_in_period(self, start: date, end: date) -> int:
        total = 0
        for e in self.time_entries:
            if e.entry_date and start <= e.entry_date <= end:
                total += e.seconds
        return total


# ---------------------------------------------------------------------------
# Utilitários de parsing (datas e tempos em PT-BR)
# ---------------------------------------------------------------------------

MONTHS_PT = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "março": 3,
    "marco": 3, "mar": 3, "abril": 4, "abr": 4, "maio": 5, "mai": 5,
    "junho": 6, "jun": 6, "julho": 7, "jul": 7, "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9, "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def parse_date_pt(text: str, today: date | None = None) -> date | None:
    """Interpreta datas como '31/12/2025', '12 de janeiro', 'hoje', 'ontem'."""
    if not text:
        return None
    today = today or date.today()
    t = _strip_accents(text.strip().lower())

    if "hoje" in t:
        return today
    if "ontem" in t:
        return date.fromordinal(today.toordinal() - 1)
    if "amanha" in t:
        return date.fromordinal(today.toordinal() + 1)

    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    # "12 de janeiro de 2026" / "12 jan" (ano corrente implícito)
    m = re.search(r"(\d{1,2})\s*(?:de\s+)?([a-z]+)\.?(?:\s*(?:de\s+)?(\d{4}))?", t)
    if m and m.group(2) in MONTHS_PT:
        d = int(m.group(1))
        mo = MONTHS_PT[m.group(2)]
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_duration_to_seconds(text: str) -> int | None:
    """Interpreta '01:30:00', '1:30', '1h 30min', '90 min', '2 h'."""
    if not text:
        return None
    t = _strip_accents(text.strip().lower())

    m = re.search(r"(\d{1,3}):(\d{2})(?::(\d{2}))?", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        s = int(m.group(3) or 0)
        return h * 3600 + mi * 60 + s

    total = 0
    found = False
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*h", t)
    if m:
        total += int(float(m.group(1).replace(",", ".")) * 3600)
        found = True
    m = re.search(r"(\d+)\s*m(?:in)?", t)
    if m:
        total += int(m.group(1)) * 60
        found = True
    m = re.search(r"(\d+)\s*s(?:eg)?", t)
    if m:
        total += int(m.group(1))
        found = True
    return total if found else None


def format_hours(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}:{m:02d}"


# ---------------------------------------------------------------------------
# Suporte a frames: o Bitrix24 renderiza fichas do CRM e detalhes de tarefa
# dentro de IFRAMES (slider lateral). Toda leitura precisa varrer o documento
# principal E os iframes — só o documento principal quase nunca tem o dado.
# ---------------------------------------------------------------------------

def _frames(page) -> list:
    """
    Todos os frames da página, com os IFRAMES PRIMEIRO: quando o slider está
    aberto, o conteúdo correto está no iframe — o documento principal ainda
    mostra a página de fundo e daria leituras erradas (ex.: título "Tarefas"
    da lista em vez do título real da tarefa).
    """
    try:
        main = page.main_frame
        others = [f for f in page.frames if f != main]
        return others + [main]
    except Exception:
        try:
            return [page.main_frame]
        except Exception:
            return []


def _eval_frames(page, js: str, arg=None) -> list:
    """Executa o JS (somente leitura) em cada frame e agrega os resultados."""
    results = []
    for frame in _frames(page):
        try:
            r = frame.evaluate(js, arg) if arg is not None else frame.evaluate(js)
            if r:
                results.append(r)
        except Exception:
            continue
    return results


def _all_frames_text(page) -> str:
    """Texto visível concatenado de todos os frames."""
    parts = _eval_frames(
        page, "() => (document.body && document.body.innerText) || ''"
    )
    return "\n".join(p for p in parts if isinstance(p, str))


def _wait_for_slider(page, timeout_ms: int = 12000) -> None:
    """
    Aguarda o conteúdo real carregar: se a página abriu um slider/iframe,
    espera o iframe ganhar corpo com texto (apenas espera — nada é clicado).
    """
    waited = 0
    step = 1000
    while waited < timeout_ms:
        for frame in _frames(page):
            try:
                if frame == page.main_frame:
                    continue
                n = frame.evaluate(
                    "() => (document.body && "
                    "document.body.innerText.trim().length) || 0"
                )
                if n and n > 200:
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                continue
        page.wait_for_timeout(step)
        waited += step




def collect_tasks_by_search(page, log: GuardLog) -> dict:
    """
    Usa a PESQUISA GLOBAL do Bitrix24 (navegação GET para /search/?q=...)
    com as variações de nome do cliente (config.SEARCH_TERMS) e coleta os
    links de tarefas dos resultados. 100% leitura: apenas navegação por URL
    e rolagem — nada é digitado em formulários nem salvo.
    """
    from urllib.parse import quote

    tasks: dict = {}
    for term in config.SEARCH_TERMS:
        url = f"{config.BASE_URL}/search/?q={quote(term)}"
        print(f"→ Pesquisa global por '{term}': {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            log.warn(f"pesquisa global por '{term}' falhou ao abrir: {e}")
            continue
        page.wait_for_timeout(4000)
        _wait_for_slider(page, 6000)

        found_this_term = 0
        stable_rounds = 0
        for _ in range(100):
            links = _collect_task_links(page)
            before = len(tasks)
            for link in links:
                m = TASK_LINK_RE.search(link["href"])
                if m:
                    tid = m.group(1)
                    title = re.sub(r"\s+", " ", link["text"]).strip()
                    if tid not in tasks:
                        tasks[tid] = {"title": title, "url": link["href"]}
                        found_this_term += 1
                    elif title and not tasks[tid]["title"]:
                        tasks[tid]["title"] = title
            if len(tasks) == before:
                stable_rounds += 1
            else:
                stable_rounds = 0
            if stable_rounds >= 3:
                break
            if not _click_load_more(page, log):
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(1500)
        print(f"  … '{term}': {found_this_term} tarefa(s) nova(s) nos resultados")

    if tasks:
        print(f"  ✓ Total de tarefas via pesquisa global: {len(tasks)}")
    else:
        log.warn(
            "a pesquisa global não retornou links de tarefas para os termos "
            f"{config.SEARCH_TERMS} — a página /search/ pode não estar "
            "disponível neste portal"
        )
    return tasks


# ---------------------------------------------------------------------------
# Localização do grupo/projeto (modo alternativo, via --group-id)
# ---------------------------------------------------------------------------

def find_group_id(page, log: GuardLog) -> str:
    """Encontra o ID do grupo do cliente pelo nome, na página de grupos."""
    if config.GROUP_ID:
        print(f"→ Usando GROUP_ID configurado: {config.GROUP_ID}")
        return str(config.GROUP_ID)

    target = _strip_accents(config.CLIENT_NAME.lower())
    print(f"→ Procurando o projeto '{config.CLIENT_NAME}' em /workgroups/ ...")
    page.goto(f"{config.BASE_URL}/workgroups/", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    prev_count = -1
    for _ in range(30):  # rolagem para carregar a lista completa
        links = []
        for chunk in _eval_frames(
            page,
            "() => Array.from(document.querySelectorAll("
            "\"a[href*='/workgroups/group/']\")).map(e => "
            "({href: e.href, text: e.textContent || ''}))",
        ):
            links.extend(chunk)
        for link in links:
            text = _strip_accents((link["text"] or "").lower())
            if target in text:
                m = re.search(r"/workgroups/group/(\d+)", link["href"])
                if m:
                    print(f"  ✓ Projeto encontrado (grupo {m.group(1)})")
                    return m.group(1)
        if len(links) == prev_count:
            break
        prev_count = len(links)
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)

    raise RuntimeError(
        f"Não foi possível localizar o projeto '{config.CLIENT_NAME}' na "
        "página /workgroups/. Abra o projeto manualmente, copie o número da "
        "URL (/workgroups/group/<ID>/) e execute com BITRIX_GROUP_ID=<ID>."
    )


# ---------------------------------------------------------------------------
# Coleta dos IDs de tarefas do grupo
# ---------------------------------------------------------------------------

TASK_LINK_RE = re.compile(r"/tasks/task/view/(\d+)/")

# Áreas globais da interface do Bitrix que exibem tarefas do PRÓPRIO usuário
# (planejador, menus, notificações, chat). Links dentro delas NÃO pertencem
# ao cliente e são ignorados na coleta.
CHROME_EXCLUDE_SELECTOR = ", ".join([
    "#bx-panel", ".bx-planner-panel", "[data-role='tasks-planner']",
    ".tasks-planner-panel", "#top_menu", ".top-menu-container",
    ".main-buttons-container", ".intranet-left-menu", "#left-menu",
    ".menu-items", ".bx-im-messenger", ".im-bar", "#bx-im-external-recent",
    ".header-search-block", "#header", ".help-block-popup",
    ".bx-notifier-panel", ".popup-window",
])


def _collect_task_links(page) -> list:
    """
    Coleta links de tarefas em TODOS os frames, apenas da área de conteúdo
    (menus/planejador/painéis globais são ignorados).
    """
    js = """
    (excludeSel) => {
      if (!document.body) return [];
      const out = [];
      document.querySelectorAll("a[href*='/tasks/task/view/']").forEach(e => {
        try { if (excludeSel && e.closest(excludeSel)) return; } catch (err) {}
        out.push({href: e.href, text: e.textContent || ''});
      });
      return out;
    }
    """
    links = []
    for chunk in _eval_frames(page, js, CHROME_EXCLUDE_SELECTOR):
        links.extend(chunk)
    return links

# Botões de paginação/carregar-mais aceitáveis (ação de navegação)
MORE_BUTTON_SELECTORS = [
    ".main-ui-pagination-load-more",
    ".main-grid-load-more",
    "span.main-ui-pagination-pages-item-more",
]
MORE_BUTTON_TEXTS = ["mostrar mais", "carregar mais", "show more", "mais"]


def _click_load_more(page, log: GuardLog) -> bool:
    """Clica no botão de paginação 'mostrar mais', se houver (leitura)."""
    for frame in _frames(page):
        for sel in MORE_BUTTON_SELECTORS:
            try:
                btn = frame.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    safe_click(btn.first, "carregar mais itens", log)
                    page.wait_for_timeout(2500)
                    return True
            except ReadOnlyViolation:
                raise
            except Exception:
                continue
        for txt in MORE_BUTTON_TEXTS:
            try:
                btn = frame.get_by_text(re.compile(rf"^\s*{txt}\s*$", re.I))
                if btn.count() > 0 and btn.first.is_visible():
                    safe_click(btn.first, "carregar mais itens", log)
                    page.wait_for_timeout(2500)
                    return True
            except ReadOnlyViolation:
                raise
            except Exception:
                continue
    return False


def collect_task_ids(page, group_id: str, log: GuardLog) -> dict:
    """
    Abre a lista de tarefas do grupo e retorna
    {task_id: {"title": ..., "url": ...}}.
    Usa rolagem e o botão 'mostrar mais' (navegação) até a lista estabilizar.
    O recorte por data é feito depois, localmente — nenhum filtro é salvo
    no Bitrix.
    """
    url = f"{config.BASE_URL}/workgroups/group/{group_id}/tasks/"
    print(f"→ Abrindo lista de tarefas: {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    _wait_for_slider(page)

    tasks: dict = {}
    stable_rounds = 0
    for round_num in range(300):
        links = _collect_task_links(page)
        before = len(tasks)
        for link in links:
            m = TASK_LINK_RE.search(link["href"])
            if m:
                tid = m.group(1)
                title = re.sub(r"\s+", " ", link["text"]).strip()
                if tid not in tasks:
                    tasks[tid] = {"title": title, "url": link["href"]}
                elif title and not tasks[tid]["title"]:
                    tasks[tid]["title"] = title

        if len(tasks) == before:
            stable_rounds += 1
        else:
            stable_rounds = 0
            print(f"  … {len(tasks)} tarefas encontradas")

        if stable_rounds >= 3:
            break

        # botão "mostrar mais" (paginação — leitura) ou rolagem (lazy-load)
        if not _click_load_more(page, log):
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(1500)

    if not tasks:
        log.warn(
            "Nenhum link de tarefa encontrado na lista do grupo. A visão "
            "padrão pode estar em Kanban/Prazos — abra o grupo e alterne "
            "para a visão 'Lista', ou verifique permissões de acesso."
        )
    else:
        print(f"  ✓ Total de tarefas na lista do grupo: {len(tasks)}")
    return tasks


# ---------------------------------------------------------------------------
# Extração do detalhe de uma tarefa
# ---------------------------------------------------------------------------

FIELD_LABELS = {
    "created": ["data de criação", "criada em", "criado em", "created"],
    "deadline": ["prazo final", "prazo", "deadline"],
    "closed": ["data de conclusão", "concluída em", "concluida em",
               "data de fechamento", "closed", "finalizada em"],
    "responsible": ["responsável", "responsavel", "assignee", "executor"],
    "time_spent": ["tempo gasto", "tempo decorrido", "tempo despendido",
                   "time spent", "elapsed time"],
    "status": ["status", "situação", "situacao"],
}

STATUS_KEYWORDS = [
    "concluída", "concluida", "concluído", "concluido", "em andamento",
    "aguardando ação", "aguardando acao", "aguardando controle",
    "supostamente concluída", "supostamente concluida", "adiada",
    "atrasada", "nova", "não iniciada", "nao iniciada", "pendente",
    "aguarda execução", "aguarda execucao",
]


def _text_after_label(page, labels: list) -> str | None:
    """
    Procura um nó cujo texto seja exatamente um dos rótulos e devolve o texto
    do elemento vizinho/pai (padrão rótulo→valor dos formulários do Bitrix).
    Executado inteiramente no DOM, sem nenhuma interação de escrita.
    """
    js = """
    (labels) => {
      if (!document.body) return null;
      const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
      const wanted = labels.map(norm);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      let node;
      while ((node = walker.nextNode())) {
        const own = norm(Array.from(node.childNodes)
          .filter(n => n.nodeType === 3).map(n => n.textContent).join(' '))
          .replace(/[:：]\\s*$/, '');
        if (!own) continue;
        if (wanted.includes(own)) {
          // 1) irmão seguinte com texto
          let sib = node.nextElementSibling;
          while (sib) {
            const t = (sib.innerText || '').trim();
            if (t) return t;
            sib = sib.nextElementSibling;
          }
          // 2) texto do pai sem o rótulo
          const parent = node.parentElement;
          if (parent) {
            const t = (parent.innerText || '').trim();
            const lbl = (node.innerText || '').trim();
            const rest = t.replace(lbl, '').trim();
            if (rest) return rest;
          }
        }
      }
      return null;
    }
    """
    for result in _eval_frames(page, js, labels):
        if result:
            return result
    return None


def _extract_status(page) -> str:
    """Lê o status exibido na página de detalhe da tarefa."""
    # 1) via rótulo "Status"
    value = _text_after_label(page, FIELD_LABELS["status"])
    if value:
        first_line = value.splitlines()[0].strip()
        if first_line:
            return first_line
    # 2) varredura por palavras de status conhecidas em elementos curtos
    js = """
    (keywords) => {
      if (!document.body) return null;
      const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase()
        .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
      const wanted = keywords.map(norm);
      const els = document.querySelectorAll('span,div,td');
      for (const el of els) {
        const t = norm(el.innerText);
        if (t && t.length < 40 && wanted.some(w => t === w || t.startsWith(w))) {
          return el.innerText.trim();
        }
      }
      return null;
    }
    """
    for found in _eval_frames(page, js, STATUS_KEYWORDS):
        if found:
            return found.strip()
    return ""


def _extract_time_entries(page, task: Task) -> None:
    """
    Lê os apontamentos de horas da tarefa.

    Procura, em qualquer tabela/lista da página de detalhe, linhas que
    combinem uma data e uma duração (HH:MM[:SS]) — formato do registro de
    tempo do Bitrix24. Se existir uma aba "Tempo decorrido"/"Registro de
    tempo", ela é aberta antes (clique de leitura, validado pela guarda).
    """
    # abre a aba de tempo, se existir (é apenas visualização)
    clicked = False
    for pattern in [r"tempo decorrido", r"registro de tempo", r"elapsed time",
                    r"tempo gasto"]:
        for frame in _frames(page):
            try:
                tab = frame.get_by_text(re.compile(pattern, re.I))
                if tab.count() > 0 and tab.first.is_visible():
                    safe_click(tab.first, f"abrir aba de tempo ({pattern})")
                    page.wait_for_timeout(2500)
                    clicked = True
                    break
            except ReadOnlyViolation:
                raise
            except Exception:
                continue
        if clicked:
            break

    js = """
    () => {
      if (!document.body) return [];
      const rows = [];
      const rowEls = document.querySelectorAll('tr, .task-elapsed-time-row, li');
      for (const el of rowEls) {
        const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
        if (!text || text.length > 400) continue;
        const dur = text.match(/\\b(\\d{1,3}:\\d{2}(?::\\d{2})?)\\b/);
        const dt = text.match(/\\b(\\d{1,2}[./]\\d{1,2}[./]\\d{2,4})\\b/);
        if (dur && dt) rows.push({text, duration: dur[1], date: dt[1]});
      }
      return rows;
    }
    """
    rows = []
    for chunk in _eval_frames(page, js):
        rows.extend(chunk)

    seen = set()
    for row in rows:
        key = (row["date"], row["duration"], row["text"][:80])
        if key in seen:
            continue
        seen.add(key)
        seconds = parse_duration_to_seconds(row["duration"]) or 0
        if seconds <= 0:
            continue
        entry_date = parse_date_pt(row["date"])
        # nome da pessoa: primeiro trecho textual antes/da linha, melhor esforço
        person = ""
        m = re.match(r"^([A-Za-zÀ-ÿ .'-]{3,50})\s", row["text"])
        if m:
            person = m.group(1).strip()
        task.time_entries.append(
            TimeEntry(entry_date=entry_date, person=person, seconds=seconds,
                      comment=row["text"][:200])
        )


def _extract_description_and_comments(page, task: Task) -> None:
    # descrição
    for sel in [".task-detail-description", "#task-detail-description",
                "[data-bx-id='task-view-description']",
                ".tasks-description", ".task-description"]:
        if task.description:
            break
        for frame in _frames(page):
            try:
                el = frame.locator(sel)
                if el.count() > 0:
                    text = el.first.inner_text(timeout=3000).strip()
                    if text:
                        task.description = re.sub(r"\s+", " ", text)[:600]
                        break
            except Exception:
                continue

    # últimos comentários (feed de discussão da tarefa)
    for sel in [".feed-com-text", ".task-comment-text",
                ".feed-com-block-inner", "[data-bx-comment-text]"]:
        if task.last_comments:
            break
        for frame in _frames(page):
            try:
                els = frame.locator(sel)
                n = els.count()
                if n > 0:
                    for i in range(max(0, n - 3), n):  # 3 mais recentes
                        txt = els.nth(i).inner_text(timeout=3000).strip()
                        txt = re.sub(r"\s+", " ", txt)
                        if txt:
                            task.last_comments.append(txt[:300])
                    break
            except Exception:
                continue


def extract_task(page, task_id: str, fallback_title: str, task_url: str,
                 log: GuardLog) -> Task:
    """Abre a página de detalhe da tarefa (por URL) e lê todos os campos."""
    task = Task(task_id=task_id, title=fallback_title)
    task.url = task_url
    page.goto(task.url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    # o detalhe da tarefa também abre em slider/iframe — aguarda carregar
    _wait_for_slider(page)

    # título (o da página vence o texto parcial do link)
    page_title = ""
    for sel in ["#pagetitle", ".pagetitle", "h1",
                ".task-detail-title", "[data-bx-title]"]:
        if page_title:
            break
        for frame in _frames(page):
            try:
                el = frame.locator(sel)
                if el.count() > 0:
                    t = re.sub(r"\s+", " ",
                               el.first.inner_text(timeout=3000)).strip()
                    if t and len(t) > 2:
                        page_title = t
                        break
            except Exception:
                continue
    if page_title:
        task.title = page_title
    if not task.title:
        task.warnings.append("título não localizado na página de detalhe")

    # status
    task.status = _extract_status(page)
    if not task.status:
        task.warnings.append("status não localizado")

    # responsável
    value = _text_after_label(page, FIELD_LABELS["responsible"])
    if value:
        task.responsible = value.splitlines()[0].strip()
    else:
        task.warnings.append("responsável não localizado")

    # datas
    for attr, labels in (("created", FIELD_LABELS["created"]),
                         ("deadline", FIELD_LABELS["deadline"]),
                         ("closed", FIELD_LABELS["closed"])):
        raw = _text_after_label(page, labels)
        if raw:
            parsed = parse_date_pt(raw.splitlines()[0])
            setattr(task, attr, parsed)
            if parsed is None:
                task.warnings.append(f"data de '{labels[0]}' ilegível: {raw[:40]}")

    # tempo gasto agregado (campo do formulário, se exibido)
    raw = _text_after_label(page, FIELD_LABELS["time_spent"])
    if raw:
        secs = parse_duration_to_seconds(raw.splitlines()[0])
        if secs is not None:
            task.total_seconds_reported = secs

    # apontamentos detalhados, descrição e comentários
    _extract_time_entries(page, task)
    _extract_description_and_comments(page, task)

    if task.total_seconds_reported and not task.time_entries:
        task.warnings.append(
            "apenas o total agregado 'Tempo gasto' estava visível; sem a "
            "lista de apontamentos, as horas do mês anterior ficam 0:00"
        )
    if task.total_seconds_reported and task.time_entries:
        detail_sum = sum(e.seconds for e in task.time_entries)
        if abs(detail_sum - task.total_seconds_reported) > 60:
            task.warnings.append(
                "soma dos apontamentos difere do campo 'Tempo gasto' "
                f"({format_hours(detail_sum)} vs "
                f"{format_hours(task.total_seconds_reported)})"
            )

    for w in task.warnings:
        log.warn(f"tarefa {task_id}: {w}")

    time.sleep(config.DELAY_BETWEEN_TASKS_S)
    return task
