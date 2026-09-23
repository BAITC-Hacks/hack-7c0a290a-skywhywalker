"""Small, deterministic SVG excerpt of observed money flows.

No inferred counterparties or amounts are drawn. Direction and edge selection
come only from the directed graph; role labels come from the analysis table.
"""

from __future__ import annotations

from base64 import b64encode
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from html import escape
from urllib.parse import urlencode


ROLE_NAMES = {
    "coordinator": "Координатор",
    "consolidator": "Консолидация",
    "distributor": "Распределитель",
    "transit": "Транзит",
    "terminal": "Конечный получатель*",
    "peripheral": "Роль не определена",
}


def _number(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return number if number.is_finite() else Decimal(0)


def _amount(value, compact=False) -> str:
    try:
        valid = Decimal(str(value)).is_finite()
    except (InvalidOperation, ValueError):
        valid = False
    if not valid:
        return "Сумма не указана"
    number = _number(value)
    if compact:
        for threshold, unit in ((10**9, "млрд"), (10**6, "млн"), (10**3, "тыс.")):
            if abs(number) >= threshold:
                digits = f"{number / threshold:.2f}".rstrip("0").rstrip(".")
                return f"{digits.replace('.', ',')} {unit} ₸"
    digits = f"{number:,.2f}".rstrip("0").rstrip(".")
    return f"{digits.replace(',', ' ').replace('.', ',')} ₸"


def _short_gid(gid) -> str:
    text = str(gid)
    return "…" + text[-9:] if len(text) > 9 else text


def _role(roles, gid) -> str:
    try:
        value = str(roles.at[gid, "role"])
    except (AttributeError, KeyError):
        value = "peripheral"
    return ROLE_NAMES.get(value, value)


def _is_seed(roles, gid) -> bool:
    try:
        value = roles.at[gid, "is_seed"]
    except (AttributeError, KeyError):
        return False
    return value is True or str(value).lower() in ("true", "1")


def _link(gid) -> str:
    return escape("?" + urlencode({"gid": str(gid), "section": "investigation"}), quote=True)


def _ys(count: int) -> list[float]:
    if count == 1:
        return [177.0]
    return [78 + index * 192 / (count - 1) for index in range(count)]


def _selected_edges(graph, gid):
    """One shared selection keeps the image and HTML hit targets aligned."""
    if gid not in graph:
        raise ValueError(f"Selected gid is not in the graph: {gid}")
    incoming = [(src, attrs) for src, _, attrs in graph.in_edges(gid, data=True) if src != gid]
    outgoing = [(dst, attrs) for _, dst, attrs in graph.out_edges(gid, data=True) if dst != gid]
    rank = lambda item: (-_number(item[1].get("sum_kzt", 0)), str(item[0]))
    return sorted(incoming, key=rank)[:3], sorted(outgoing, key=rank)[:4]


def render_flow_svg(graph, roles, gid: int) -> str:
    """Return a responsive 780×340 SVG with ≤3 incoming and ≤4 outgoing edges.

    Each side is independently ranked by ``sum_kzt`` (then GID for stable ties).
    A mutual counterparty may appear once on each side because those are two
    distinct directed edges. A self-transfer is shown once as a centre loop and
    does not consume a counterparty slot. Node links use full, lossless GIDs.
    ``roles`` is the pipeline DataFrame indexed by gid. The graph is a DiGraph.
    """
    incoming, outgoing = _selected_edges(graph, gid)
    loop = graph.get_edge_data(gid, gid)
    token = sha1(str(gid).encode()).hexdigest()[:12]
    prefix = f"mm-flow-{token}"
    role = _role(roles, gid)
    eid, erole = escape(str(gid)), escape(role)

    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" class="mm-flow-svg" viewBox="0 0 780 340" width="100%" role="img" aria-labelledby="{prefix}-title {prefix}-desc" style="display:block;width:100%;height:auto;font-family:Inter,Arial,sans-serif">
<title id="{prefix}-title">Наблюдаемые денежные потоки узла {eid}</title>
<desc id="{prefix}-desc">Направление слева направо: плательщики, выбранный узел, получатели. Показаны крупнейшие входящие и исходящие связи по сумме переводов. Нажмите на узел, чтобы открыть его расследование.</desc>
<defs>
  <pattern id="{prefix}-dots" width="13" height="13" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.75" fill="#D5E4DC"/></pattern>
  <marker id="{prefix}-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L8 4 L0 8 L2 4 Z" fill="#4D9965"/></marker>
  <linearGradient id="{prefix}-left" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#62BE4E"/><stop offset="1" stop-color="#379E42"/></linearGradient>
  <linearGradient id="{prefix}-right" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#CDF1D2"/><stop offset="1" stop-color="#97DEAD"/></linearGradient>
  <filter id="{prefix}-shadow" x="-20%" y="-30%" width="140%" height="170%"><feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#164B32" flood-opacity="0.12"/></filter>
</defs>
<rect x="0.5" y="0.5" width="779" height="339" rx="14" fill="#FCFEFD" stroke="#E3EBE6"/>
<rect x="1" y="47" width="778" height="276" rx="12" fill="url(#{prefix}-dots)"/>
<g fill="#6D8177" font-size="10" font-weight="700" letter-spacing="1.1">
<text x="109" y="29" text-anchor="middle">ПЛАТЕЛЬЩИКИ</text>
<text x="392" y="29" text-anchor="middle">ВЫБРАННЫЙ УЗЕЛ</text>
<text x="661" y="29" text-anchor="middle">ПОЛУЧАТЕЛИ</text>
</g>''']

    for side, edges in (("in", incoming), ("out", outgoing)):
        for index, ((node, attrs), y) in enumerate(zip(edges, _ys(len(edges)))):
            amount = attrs.get("sum_kzt")
            exact = _amount(amount)
            abbreviated = _amount(amount, compact=True)
            src, dst = (node, gid) if side == "in" else (gid, node)
            edge_title = escape(f"{src} → {dst}: {exact}")
            if "n_tx" in attrs:
                edge_title += escape(f" · переводов: {attrs['n_tx']}")
            # Endpoints are attached to the central card, but fan out gently.
            attach_y = 177 + (index - (len(edges) - 1) / 2) * 13
            if side == "in":
                path = f"M78 {y:g} C207 {y:g}, 249 {attach_y:g}, 307 {attach_y:g}"
                label_x = 236
            else:
                path = f"M477 {attach_y:g} C537 {attach_y:g}, 568 {y:g}, 616 {y:g}"
                label_x = 547
            label_y = (y + attach_y) / 2 - 9
            parts.append(f'''<g class="mm-flow-edge" data-src="{escape(str(src), quote=True)}" data-dst="{escape(str(dst), quote=True)}">
<title>{edge_title}</title>
<path d="{path}" fill="none" stroke="#66A87B" stroke-width="1.65" stroke-linecap="round" marker-end="url(#{prefix}-arrow)"/>
<rect x="{label_x-47}" y="{label_y-10:g}" width="94" height="16" rx="6" fill="#FCFEFD" fill-opacity="0.96"/>
<text x="{label_x}" y="{label_y:g}" text-anchor="middle" fill="#698074" font-size="9.5">{escape(abbreviated)}</text>
</g>''')

    if loop is not None:
        exact = _amount(loop.get("sum_kzt"))
        abbreviated = _amount(loop.get("sum_kzt"), compact=True)
        parts.append(f'''<g class="mm-flow-self" data-src="{eid}" data-dst="{eid}"><title>{eid} → {eid}: {escape(exact)} · перевод внутри одного узла</title>
<path d="M359 141 C341 79, 444 79, 427 140" fill="none" stroke="#66A87B" stroke-width="1.65" marker-end="url(#{prefix}-arrow)"/>
<rect x="335" y="67" width="115" height="33" rx="7" fill="#FCFEFD"/>
<text x="392" y="80" text-anchor="middle" fill="#6D8177" font-size="9">Внутри узла</text>
<text x="392" y="93" text-anchor="middle" fill="#4F6C5D" font-size="10">{escape(abbreviated)}</text></g>''')

    for side, edges in (("in", incoming), ("out", outgoing)):
        for (node, _), y in zip(edges, _ys(len(edges))):
            x = 54 if side == "in" else 641
            label_x = 87 if side == "in" else 676
            fill = "left" if side == "in" else "right"
            icon = "#FFFFFF" if side == "in" else "#23643A"
            status = "Исходный клиент" if _is_seed(roles, node) else "Связанный узел"
            node_title = escape(f"GID {node} · {_role(roles, node)} · {status}")
            parts.append(f'''<a class="mm-flow-node" href="{_link(node)}" target="_self" aria-label="{escape(f'Открыть узел {node}', quote=True)}" style="cursor:pointer">
<title>{node_title}</title>
<circle cx="{x}" cy="{y:g}" r="24" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="5"/>
<circle cx="{x}" cy="{y:g}" r="23" fill="url(#{prefix}-{fill})"/>
<circle cx="{x}" cy="{y:g}" r="7" fill="none" stroke="{icon}" stroke-width="1.8"/>
<circle cx="{x}" cy="{y:g}" r="2.4" fill="{icon}"/>
<circle cx="{x+11}" cy="{y-8:g}" r="2.5" fill="{icon}"/>
<path d="M{x+5} {y-4:g} L{x+9} {y-7:g}" stroke="{icon}" stroke-width="1.8"/>
<rect x="{label_x-3}" y="{y-16:g}" width="99" height="32" rx="5" fill="#FCFEFD" fill-opacity="0.97"/>
<text x="{label_x}" y="{y-3:g}" fill="#254E39" font-size="12" font-weight="600">{escape(_short_gid(node))}</text>
<text x="{label_x}" y="{y+12:g}" fill="#8A9C91" font-size="9">{status}</text>
</a>''')

    badge = "Исходный клиент" if _is_seed(roles, gid) else "Узел в фокусе"
    visible_role = role if len(role) <= 23 else role[:22] + "…"
    parts.append(f'''<a class="mm-flow-selected" href="{_link(gid)}" target="_self" aria-label="{escape(f'Открыть выбранный узел {gid}', quote=True)}" style="cursor:pointer">
<title>GID {eid} · {erole}</title>
<rect x="307" y="141" width="170" height="72" rx="17" fill="#164B32" filter="url(#{prefix}-shadow)"/>
<circle cx="330" cy="176" r="9" fill="none" stroke="#AFD9BB" stroke-width="1.6"/>
<circle cx="330" cy="176" r="3" fill="#FFFFFF"/>
<text x="351" y="175" fill="#FFFFFF" font-size="14" font-weight="700">{escape(_short_gid(gid))}</text>
<text x="351" y="193" fill="#D1E8D9" font-size="10">{escape(visible_role)}</text>
<rect x="344" y="222" width="96" height="19" rx="9.5" fill="#ECF5EF"/>
<text x="392" y="235" text-anchor="middle" fill="#71917D" font-size="9">{badge}</text>
</a>''')

    if not incoming:
        label = "Нет входящих в выгрузке"
        parts.append(f'<text x="125" y="180" text-anchor="middle" fill="#9AA99F" font-size="11">{label}</text>')
    if not outgoing:
        label = "Нет исходящих в выгрузке"
        parts.append(f'<text x="644" y="180" text-anchor="middle" fill="#9AA99F" font-size="11">{label}</text>')
    if not incoming and not outgoing and loop is None:
        parts.append('<text x="392" y="250" text-anchor="middle" fill="#7E9285" font-size="11">У узла нет наблюдаемых переводов</text>')
    parts.append('</svg>')
    return "".join(parts)


def render_flow_html(graph, roles, gid: int) -> str:
    """Render the safe SVG as an image, with responsive native HTML links.

    Streamlit's HTML sanitizer removes inline SVG. An inert SVG image preserves
    the diagram without disabling sanitization or executing JavaScript. HTML
    anchor overlays provide keyboard access, hover labels, and node navigation;
    their percentages use the same coordinates as the 780×340 image.
    """
    incoming, outgoing = _selected_edges(graph, gid)
    image = b64encode(render_flow_svg(graph, roles, gid).encode("utf-8")).decode("ascii")
    alt = escape(f"Денежные потоки узла {gid}: плательщики слева, получатели справа", quote=True)
    parts = [
        '<div class="mm-flow-interactive" style="position:relative;width:100%;aspect-ratio:780 / 340">',
        f'<img class="mm-flow-image" src="data:image/svg+xml;base64,{image}" alt="{alt}" width="780" height="340" style="display:block;width:100%;height:auto" />',
    ]

    def overlay(node, x, y, width, height, selected=False, amount=None):
        status = "Исходный клиент" if _is_seed(roles, node) else "Связанный узел"
        title = f"GID {node} · {_role(roles, node)} · {status}"
        if amount is not None:
            title += f" · {_amount(amount)}"
        label = f"Открыть {'выбранный ' if selected else ''}узел {node}: {_role(roles, node)}"
        style = (
            f"position:absolute;display:block;left:{x / 780 * 100:.5f}%;"
            f"top:{y / 340 * 100:.5f}%;width:{width / 780 * 100:.5f}%;"
            f"height:{height / 340 * 100:.5f}%;border-radius:14px;"
            "background:transparent;cursor:pointer"
        )
        selected_class = " mm-flow-hotspot-selected" if selected else ""
        return (
            f'<a class="mm-flow-hit mm-flow-hotspot{selected_class}" href="{_link(node)}" target="_self" '
            f'title="{escape(title, quote=True)}" aria-label="{escape(label, quote=True)}" '
            f'data-node-gid="{escape(str(node), quote=True)}" style="{style}"></a>'
        )

    for side, edges in (("in", incoming), ("out", outgoing)):
        x, width = (30, 160) if side == "in" else (618, 159)
        for (node, attrs), y in zip(edges, _ys(len(edges))):
            parts.append(overlay(node, x, y - 24, width, 48, amount=attrs.get("sum_kzt")))
    # Self-transfers were excluded from counterparties above; the centre has
    # exactly one navigation target, even when the graph contains a self-loop.
    parts.append(overlay(gid, 307, 141, 170, 72, selected=True))
    parts.append('</div>')
    return "".join(parts)
