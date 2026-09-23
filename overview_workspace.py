"""Data-backed HTML for the compact MoneyMap investigation overview."""

from __future__ import annotations

from base64 import b64encode
from html import escape
from urllib.parse import urlencode

import pandas as pd

from flow_visual import render_flow_html


ROLE_NAMES = {
    "coordinator": "Координатор",
    "consolidator": "Консолидация",
    "distributor": "Распределитель",
    "transit": "Транзит",
    "terminal": "Получатель без видимого выхода",
    "peripheral": "Роль не определена",
}

_ICONS = {
    "people": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87"/><circle cx="9" cy="7" r="4"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "network": '<circle cx="12" cy="4" r="2.5"/><circle cx="5" cy="19" r="2.5"/><circle cx="19" cy="19" r="2.5"/><path d="m11 6-5 10m7-10 5 10"/>',
    "transfer": '<path d="M4 7h16m-5-5 5 5-5 5M20 17H4m5-5-5 5 5 5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
    "arrow": '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.01"/>',
}


def icon(name: str) -> str:
    """An intentionally small, consistent code-native icon set."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
        'fill="none" stroke="#4F8D3E" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        f'focusable="false">{_ICONS[name]}</svg>'
    )
    encoded = b64encode(svg.encode("utf-8")).decode("ascii")
    return (
        '<img class="mm-icon" width="20" height="20" '
        f'src="data:image/svg+xml;base64,{encoded}" alt="" aria-hidden="true">'
    )


def _plural(number: int, one: str, few: str, many: str) -> str:
    if 11 <= number % 100 <= 14:
        return many
    return one if number % 10 == 1 else few if 2 <= number % 10 <= 4 else many


def _count(number: int) -> str:
    return f"{number:,}".replace(",", " ")


def _link(section: str, gid: str | None = None) -> str:
    params = {"section": section}
    if gid is not None:
        params["gid"] = gid
    return escape("?" + urlencode(params), quote=True)


def _period(tx, roles) -> str:
    dates = pd.to_datetime(tx["date"]).dropna()
    if dates.empty:
        period = "Период не указан"
    else:
        first, last = dates.min(), dates.max()
        months = (
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
        )
        period = (
            f"{months[first.month - 1]} {first.year}"
            if (first.year, first.month) == (last.year, last.month)
            else f"{first:%d.%m.%Y} — {last:%d.%m.%Y}"
        )
    depth = int(roles["depth"].max())
    return f"{period} · {depth} {_plural(depth, 'колено', 'колена', 'колен')}"


def render_overview(graph, roles, top, tx) -> str:
    """Return one cohesive overview; every identifier and statistic is real.

    ``roles`` is indexed by the original integer GID. Identifiers are converted
    directly to strings for HTML and navigation, never through a float.
    """
    if top.empty:
        return '<section class="mm-overview"><h1>Очередь проверки пуста</h1><p>Нет рассчитанных кандидатов для отображения.</p></section>'

    selected = int(top.iloc[0]["gid"])
    selected_gid = str(selected)
    row = roles.loc[selected]
    role = str(row["role"])
    role_name = ROLE_NAMES.get(role, role)
    first_rank = int(top.iloc[0]["rank"])

    stat_items = (
        ("people", int(roles["is_seed"].sum()), "Исходных клиентов"),
        ("network", len(roles), "Узлов в сети"),
        ("transfer", len(tx), "Переводов"),
        ("clock", len(top), "В очереди проверки"),
    )
    stats = "".join(
        f'<div class="mm-stat"><span class="mm-stat-icon">{icon(name)}</span>'
        f'<div class="mm-stat-copy"><strong>{_count(value)}</strong>'
        f'<span>{escape(label)}</span></div></div>'
        for name, value, label in stat_items
    )

    incoming, outgoing, reach = int(row["in_deg"]), int(row["out_deg"]), int(row["seed_reach"])
    signal_items = (
        (f"{incoming} {_plural(incoming, 'плательщик', 'плательщика', 'плательщиков')}", "Наблюдаемые входящие контрагенты"),
        (f"{outgoing} {_plural(outgoing, 'получатель', 'получателя', 'получателей')}", "Наблюдаемые исходящие контрагенты"),
        (f"Достижим из {reach} {_plural(reach, 'исходного клиента', 'исходных клиентов', 'исходных клиентов')}", "Направленные пути в пределах четырёх колен"),
    )
    signals = "".join(
        f'<div class="mm-signal"><span class="mm-check">{icon("check")}</span>'
        f'<div><strong>{escape(title)}</strong><small>{escape(detail)}</small></div></div>'
        for title, detail in signal_items
    )

    queue_rows = []
    for candidate in top.head(3).itertuples(index=False):
        gid = str(candidate.gid)
        candidate_role = str(candidate.role)
        label = ROLE_NAMES.get(candidate_role, candidate_role)
        href = _link("investigation", gid)
        queue_rows.append(
            f'<tr><td class="mm-rank">{int(candidate.rank)}</td>'
            f'<td class="mm-gid"><a href="{href}" target="_self">{escape(gid)}</a></td>'
            f'<td><span class="mm-role-chip" data-role="{escape(candidate_role, quote=True)}">{escape(label)}</span></td>'
            f'<td class="mm-score-cell">{float(candidate.priority_score):.3f}</td>'
            f'<td class="mm-table-action"><a href="{href}" target="_self" '
            f'aria-label="Изучить узел {escape(gid, quote=True)}">Изучить {icon("arrow")}</a></td></tr>'
        )

    step_items = (
        ("Выберите узел", "Из очереди или по полному gid"),
        ("Изучите связи", "Направления, суммы и роли"),
        ("Проверьте основания", "Факты и ограничения данных"),
    )
    steps = []
    for number, (title, detail) in enumerate(step_items, 1):
        steps.append(
            f'<div class="mm-step"><span class="mm-step-number">{number}</span>'
            f'<div><strong>{escape(title)}</strong><small>{escape(detail)}</small></div></div>'
        )
        if number < len(step_items):
            steps.append(f'<span class="mm-step-arrow">{icon("arrow")}</span>')

    flow = render_flow_html(graph, roles, selected)
    return f'''<section class="mm-overview" aria-label="Обзор дела MoneyMap">
      <div class="mm-page-meta"><span>Рабочее место AML-аналитика</span><span class="mm-date">{icon("calendar")}{escape(_period(tx, roles))}</span></div>
      <header class="mm-heading"><h1>Кого проверить следующим?</h1><p>Находим значимые узлы и объясняем движение денег.</p></header>
      <div class="mm-stats">{stats}</div>
      <div class="mm-workspace">
        <section class="mm-panel mm-graph-panel" aria-labelledby="mm-flow-heading">
          <div class="mm-panel-heading"><h2 id="mm-flow-heading">Как движутся деньги</h2><p>Первый узел в очереди · крупнейшие прямые связи</p></div>
          <div class="mm-flow-wrap">{flow}</div>
          <div class="mm-legend"><span><i class="mm-dot mm-dot-selected"></i>Выбранный узел</span><span><i class="mm-dot mm-dot-in"></i>Плательщик</span><span><i class="mm-dot mm-dot-out"></i>Получатель</span><span>{icon("arrow")}Направление перевода</span></div>
          <p class="mm-map-note">Показан фрагмент сети. Все переводы выбранного узла доступны в расследовании.</p>
        </section>
        <section class="mm-panel mm-score-panel" aria-labelledby="mm-priority-heading">
          <span class="mm-priority-pill">ПРИОРИТЕТ № {first_rank}</span>
          <h2 id="mm-priority-heading">Проверить связи узла</h2>
          <div class="mm-selected-id">gid {escape(selected_gid)} <span class="mm-role-chip" data-role="{escape(role, quote=True)}">{escape(role_name)}</span></div>
          <div class="mm-score">{float(row['priority_score']):.3f}</div>
          <div class="mm-score-caption">Приоритет проверки <span title="Очередность ручного анализа, не вероятность правонарушения">{icon("info")}</span></div>
          <div class="mm-signals">{signals}</div>
          <a class="mm-primary" href="{_link('investigation', selected_gid)}" target="_self">Открыть расследование {icon("arrow")}</a>
          <div class="mm-advisory">{icon("info")}<span>Гипотеза, не доказательство нарушения.</span></div>
        </section>
      </div>
      <section class="mm-panel mm-queue" aria-labelledby="mm-queue-heading">
        <div class="mm-queue-heading"><h2 id="mm-queue-heading">Очередь проверки</h2><div><span>Первые {min(3, len(top))} из {len(top)}</span><a class="mm-queue-link" href="{_link('priorities')}" target="_self">Вся очередь {icon("arrow")}</a></div></div>
        <div class="mm-table-wrap"><table><thead><tr><th scope="col">№</th><th scope="col">Узел (GID)</th><th scope="col">Роль в сети</th><th scope="col">Приоритет</th><th scope="col">Действие</th></tr></thead><tbody>{''.join(queue_rows)}</tbody></table></div>
      </section>
      <div class="mm-steps">{''.join(steps)}</div>
    </section>'''
