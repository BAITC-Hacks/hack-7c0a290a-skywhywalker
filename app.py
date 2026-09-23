"""MoneyMap investigation UI. Start with: streamlit run app.py"""

from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pipeline import load_data, make_graph


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"
ROLE_NAMES = {
    "coordinator": "Координатор",
    "consolidator": "Консолидация",
    "distributor": "Распределитель",
    "transit": "Транзит",
    "terminal": "Конечный получатель*",
    "peripheral": "Периферия / неопределённо",
}
ROLE_COLORS = {
    "coordinator": "#D9514E",
    "consolidator": "#208B4D",
    "distributor": "#8156B8",
    "transit": "#208FA1",
    "terminal": "#80A85B",
    "peripheral": "#9BA99D",
}


st.set_page_config(page_title="MoneyMap · AML аналитика", page_icon="◉", layout="wide")
st.markdown(f'<style>{(ROOT / "ui.css").read_text()}</style>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def read_analysis():
    roles = pd.read_csv(OUT / "nodes_roles.csv").set_index("gid", drop=False)
    clusters = pd.read_csv(OUT / "clusters.csv")
    top = pd.read_csv(OUT / "top_nodes.csv")
    nodes, edges, tx = load_data(DATA)
    return roles, clusters, top, nodes, edges, tx


@st.cache_resource(show_spinner=False)
def graph_from_edges(_nodes: pd.DataFrame, _edges: pd.DataFrame):
    return make_graph(_nodes, _edges)


def selected_subgraph(graph: nx.DiGraph, roles: pd.DataFrame, selected: int, radius: int, max_nodes: int = 17):
    neighbors = nx.single_source_shortest_path_length(graph.to_undirected(), selected, cutoff=radius)
    members = set(neighbors)
    if len(members) > max_nodes:
        scores = []
        for gid in members - {selected}:
            amount = sum(
                attrs["sum_kzt"]
                for src, dst, attrs in graph.in_edges(gid, data=True)
                if src == selected or dst == selected
            ) + sum(
                attrs["sum_kzt"]
                for src, dst, attrs in graph.out_edges(gid, data=True)
                if src == selected or dst == selected
            )
            scores.append((amount, roles.at[gid, "priority_score"], gid))
        scores.sort(reverse=True)
        # Reserve room for both incoming and outgoing flows; a high-volume side
        # must not erase the other side of the story in the compact view.
        members = {selected}
        quota = (max_nodes - 1) // 2
        for candidates in (set(graph.predecessors(selected)), set(graph.successors(selected))):
            members.update(gid for _, _, gid in [s for s in scores if s[2] in candidates][:quota])
        for _, _, gid in scores:
            if len(members) >= max_nodes:
                break
            members.add(gid)
    view = graph.subgraph(members).copy()
    if radius == 1:
        view.remove_edges_from([(u, v) for u, v in view.edges if selected not in (u, v)])
    return view


def one_hop_positions(view: nx.DiGraph, selected: int):
    """Keep payers left and recipients right so arrow direction is easy to read."""
    incoming = sorted(set(view.predecessors(selected)) - {selected})
    outgoing = sorted(set(view.successors(selected)) - {selected})
    both = set(incoming) & set(outgoing)
    incoming = [gid for gid in incoming if gid not in both]
    outgoing = [gid for gid in outgoing if gid not in both]
    positions = {selected: (0.0, 0.0)}
    for gids, x in ((incoming, -1.0), (outgoing, 1.0), (sorted(both), 0.75)):
        count = len(gids)
        for index, gid in enumerate(gids):
            positions[gid] = (x, 1.0 - 2.0 * (index + 1) / (count + 1))
    return positions


def network_figure(graph: nx.DiGraph, roles: pd.DataFrame, selected: int, radius: int, max_nodes: int = 17, compact: bool = False):
    view = selected_subgraph(graph, roles, selected, radius, max_nodes)
    if view.number_of_nodes() == 1:
        return None, view
    positions = (
        one_hop_positions(view, selected)
        if radius == 1 else nx.spring_layout(view.to_undirected(), seed=17, weight=None, iterations=90)
    )
    edge_x, edge_y, annotations = [], [], []
    for src, dst, attrs in view.edges(data=True):
        x0, y0 = positions[src]
        x1, y1 = positions[dst]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        # Arrowhead placed before the destination point so it remains visible.
        arrow_x, arrow_y = x0 + 0.83 * (x1 - x0), y0 + 0.83 * (y1 - y0)
        tail_x, tail_y = x0 + 0.65 * (x1 - x0), y0 + 0.65 * (y1 - y0)
        annotations.append(dict(
            x=arrow_x, y=arrow_y, ax=tail_x, ay=tail_y, xref="x", yref="y",
            axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=0.85,
            arrowwidth=1.3, arrowcolor="#66816A", text="",
        ))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines", line=dict(width=1.2, color="#A4B8A6"),
        hoverinfo="skip", showlegend=False,
    ))
    for role, color in ROLE_COLORS.items():
        gids = [gid for gid in view.nodes if roles.at[gid, "role"] == role]
        if not gids:
            continue
        fig.add_trace(go.Scatter(
            x=[positions[gid][0] for gid in gids],
            y=[positions[gid][1] for gid in gids],
            mode="markers+text",
            text=["…" + str(gid)[-9:] if len(view) <= 21 or gid == selected else "" for gid in gids],
            textposition="bottom center", textfont=dict(color="#385246", size=11),
            marker=dict(
                color=color,
                size=[42 if gid == selected else 17 + 10 * roles.at[gid, "priority_score"] for gid in gids],
                line=dict(color="#FFFFFF", width=2),
            ),
            customdata=[[str(gid), roles.at[gid, "evidence"]] for gid in gids],
            hovertemplate="gid %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
            name=ROLE_NAMES[role],
        ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        height=350 if compact else 480, margin=dict(l=35, r=35, t=35, b=20),
        xaxis=dict(visible=False, range=[-1.5, 1.5] if radius == 1 else None),
        yaxis=dict(visible=False, range=[-1.2, 1.3] if radius == 1 else None),
        annotations=annotations, legend=dict(orientation="h", y=-0.08, x=0, font=dict(size=10)),
        font=dict(color="#294B32"), hoverlabel=dict(bgcolor="#EAF5E9", font_color="#173A25"),
    )
    if radius == 1:
        for x, label in ((-1, "ПЛАТЕЛЬЩИКИ"), (0, "ВЫБРАННЫЙ УЗЕЛ"), (1, "ПОЛУЧАТЕЛИ")):
            fig.add_annotation(x=x, y=1.13, text=label, showarrow=False, font=dict(color="#6B8074", size=10))
    return fig, view


def shortest_seed_path(graph: nx.DiGraph, roles: pd.DataFrame, gid: int):
    seeds = roles.loc[roles.is_seed, "gid"].astype(int).tolist()
    best = None
    for seed in seeds:
        try:
            path = nx.shortest_path(graph, source=seed, target=gid)
        except nx.NetworkXNoPath:
            continue
        if best is None or len(path) < len(best):
            best = path
    return best


def fmt_kzt(value):
    return f"{value:,.0f} ₸".replace(",", " ")


def investigation_facts(selected: int, row: pd.Series, related: pd.DataFrame, path: list[int] | None):
    """Only observed, anonymized facts for an optional AI-written case note."""
    counterparties = related.sort_values("sum_kzt", ascending=False).head(8)
    return {
        "gid": selected,
        "role": row.role,
        "role_evidence": row.evidence,
        "role_score": float(row.role_score),
        "priority_score": float(row.priority_score),
        "depth": int(row.depth),
        "is_seed": bool(row.is_seed),
        "truncated_by_depth": bool(row.truncated_by_depth),
        "in_deg": int(row.in_deg),
        "out_deg": int(row.out_deg),
        "in_kzt": float(row.in_kzt),
        "out_kzt": float(row.out_kzt),
        "seed_reach": int(row.seed_reach),
        "fast_forward_fraction": float(row.fast_forward),
        "shortest_observed_seed_path": path,
        "largest_observed_edges": [
            {"src": int(r.src), "dst": int(r.dst), "sum_kzt": float(r.sum_kzt), "n_tx": int(r.n_tx)}
            for r in counterparties.itertuples(index=False)
        ],
    }


def generate_case_note(facts: dict, api_key: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), timeout=20.0)
    result = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
        reasoning={"effort": "none"},
        instructions=(
            "Ты помощник AML-аналитика. Напиши краткую справку на русском по ТОЛЬКО переданным фактам. "
            "Три раздела: 'Наблюдения', 'Гипотеза', 'Что проверить дальше'. "
            "Приводи конкретные gid и суммы, если они есть. Не придумывай личность, источник денег, "
            "виновность или связи за пределами выгрузки. Помни: входящие seed неполны, глубина 4 "
            "обрезана, быстрый выход не доказывает прохождение тех же денег. "
            "Гипотезу формулируй условно. Не более 180 слов."
        ),
        input=json.dumps(facts, ensure_ascii=False),
        max_output_tokens=500,
        store=False,
    )
    return result.output_text


if not all((DATA / f"{name}.parquet").exists() for name in ("nodes", "edges", "transactions")):
    st.error("Положите nodes.parquet, edges.parquet и transactions.parquet в папку data/ и перезапустите приложение.")
    st.stop()

if not all((OUT / name).exists() for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")):
    st.info("Готовлю аналитические выгрузки из исходных данных…")
    import sys
    from pipeline import main

    previous_argv = sys.argv
    try:
        sys.argv = ["pipeline.py", "--data", str(DATA), "--out", str(OUT)]
        main()
    finally:
        sys.argv = previous_argv

roles, clusters, top, nodes, edges, tx = read_analysis()
graph = graph_from_edges(nodes, edges)

default_gid = int(top.iloc[0].gid)
if "section" not in st.session_state:
    st.session_state.section = "Обзор"
if "gid_input" not in st.session_state:
    st.session_state.gid_input = str(default_gid)
if "pending_gid" in st.session_state:
    st.session_state.gid_input = str(st.session_state.pop("pending_gid"))
if "pending_section" in st.session_state:
    st.session_state.section = st.session_state.pop("pending_section")
route_sections = {"overview": "Обзор", "investigation": "Расследование", "priorities": "Приоритеты", "clusters": "Кластеры", "method": "Методика"}
if st.query_params.get("section") in route_sections:
    st.session_state.section = route_sections[st.query_params["section"]]
    route_gid = st.query_params.get("gid", "")
    if route_gid.isdigit() and int(route_gid) in roles.index:
        st.session_state.gid_input = route_gid
    st.query_params.clear()


def open_gid(gid: int) -> None:
    st.session_state.pending_gid = int(gid)
    st.session_state.pending_section = "Расследование"
    st.rerun()


st.sidebar.markdown('<div class="brand"><span class="brand-mark">≋</span><div><strong>MoneyMap</strong><small>Граф денег</small></div></div>', unsafe_allow_html=True)
section = st.sidebar.radio("Рабочее место", ["Обзор", "Расследование", "Приоритеты", "Кластеры", "Методика"], key="section", label_visibility="collapsed", format_func=lambda name: "Обзор дела" if name == "Обзор" else name)
st.sidebar.divider()
gid_text = st.sidebar.text_input("Поиск по gid", key="gid_input")
if not gid_text.isdigit() or int(gid_text) not in roles.index:
    st.sidebar.error("Укажите gid из набора данных")
    selected = default_gid
else:
    selected = int(gid_text)
if st.sidebar.button("Открыть узел →", use_container_width=True):
    st.session_state.pending_section = "Расследование"
    st.rerun()
st.sidebar.divider()
st.sidebar.caption("HackAlem AI · Финансы\n\nОбезличенные данные · локальный анализ")

if section == "Обзор":
    from overview_workspace import render_overview
    st.html(render_overview(graph, roles, top, tx))
    with st.expander("Что важно для оценки жюри"):
        st.markdown("""
        **Проблема и ценность (15):** понятный сценарий AML-аналитика и приоритет проверки.
        **Функциональность (25):** три CSV и поиск любого gid в веб-интерфейсе.
        **Техническая реализация (15):** воспроизводимый расчёт по parquet.
        **Практическая применимость (15):** численные основания и ограничения данных.
        **Потенциал развития (20):** повторные выгрузки, обратная связь аналитика, дополнительные источники — план, не функции текущей версии.
        **README и воспроизводимость (10):** команда запуска и сценарий проверки в репозитории.
        """)

elif section == "Расследование":
    st.markdown('<div class="eyebrow">ОЧЕРЕДЬ ПРОВЕРКИ / РАССЛЕДОВАНИЕ</div>', unsafe_allow_html=True)
    st.title("Связи и основания")
    st.caption("Сначала изучите движение денег, затем сопоставьте гипотезу с наблюдаемыми фактами.")
    row = roles.loc[selected]
    left, right = st.columns([1.8, 1], gap="medium")
    with left, st.container(border=True, key="investigation_map"):
        st.subheader("Карта переводов")
        st.caption(f"Выбранный узел: {selected}")
        simple_tab, network_tab = st.tabs(["Схема потоков", "Исследовать граф"])
        with simple_tab:
            from flow_visual import render_flow_html
            st.html('<div class="mm-flow-wrap">' + render_flow_html(graph, roles, selected) + '</div>')
            st.caption("Крупнейшие связи: до 3 входящих и 4 исходящих. Нажмите на узел, чтобы продолжить проверку. Полный список переводов — ниже.")
        with network_tab:
            controls_a, controls_b = st.columns(2)
            radius = controls_a.radio("Глубина обзора", [1, 2], horizontal=True, format_func=lambda n: "Прямые связи" if n == 1 else "Два шага")
            max_nodes = controls_b.selectbox("Плотность карты", [9, 17, 33, 65], index=1, format_func=lambda n: f"До {n} узлов")
            figure, view = network_figure(graph, roles, selected, radius, max_nodes=max_nodes)
            if figure:
                st.plotly_chart(figure, width="stretch")
                st.caption(f"Фрагмент: {len(view)} узлов, {view.number_of_edges()} направленных рёбер. Для прямых связей оставлены только переводы выбранного узла; лимит сохраняет обе стороны потока.")
            else:
                st.info("У этого gid нет наблюдаемых рёбер в выгрузке.")
    with right, st.container(border=True, key="investigation_details"):
        st.markdown('<span class="priority-pill">ГИПОТЕЗА ПО УЗЛУ</span>', unsafe_allow_html=True)
        st.subheader(ROLE_NAMES[row.role])
        st.caption(f"gid {selected}")
        st.markdown(f"**Приоритет:** {row.priority_score:.3f} · **сила признака:** {row.role_score:.0%}")
        st.caption(f"Кластер {int(row.cluster_id)} · колено {int(row.depth)} · не оценка виновности")
        st.markdown(f'<div class="case-note">{escape(row.evidence)}</div>', unsafe_allow_html=True)
        m1, m2 = st.columns(2)
        m1.metric("Получено в графе", fmt_kzt(row.in_kzt))
        m2.metric("Отправлено в графе", fmt_kzt(row.out_kzt))
        m3, m4 = st.columns(2)
        m3.metric("Плательщиков", int(row.in_deg))
        m4.metric("Получателей", int(row.out_deg))
        st.write(f"Достижим из **{int(row.seed_reach)}** исходных seed; доля быстрых выходов после поступления — **{row.fast_forward:.0%}**.")
        path = shortest_seed_path(graph, roles, selected)
        if path:
            with st.expander("Путь от исходного клиента"):
                for step, path_gid in enumerate(path):
                    st.text(f"{step + 1}. {path_gid}")
        else:
            st.write("Наблюдаемого пути от seed нет.")
        if row.truncated_by_depth:
            st.warning("Исходящие на глубине 4 обрезаны процедурой выгрузки. Отсутствие перевода здесь не доказывает удержание денег.")
        if row.is_seed:
            st.info("У seed входящие из-за границ выгрузки неизвестны; отношение отправлено/получено для него не трактуется как баланс.")
    st.subheader("Наблюдаемые переводы")
    related = edges.loc[(edges.src == selected) | (edges.dst == selected)].copy()
    related["направление"] = related.apply(
        lambda r: "исходящий →" if r.src == selected else "← входящий", axis=1
    )
    related = related.sort_values("sum_kzt", ascending=False)
    related[["src", "dst"]] = related[["src", "dst"]].astype(str)
    st.dataframe(
        related[["направление", "src", "dst", "sum_kzt", "n_tx", "depth"]].rename(columns={
            "src": "плательщик", "dst": "получатель", "sum_kzt": "сумма ₸",
            "n_tx": "транзакций", "depth": "колено",
        }),
        hide_index=True, width="stretch", height=280,
    )
    st.subheader("Краткая AI-справка")
    with st.expander("Подключить OpenAI для текстовой справки"):
        st.caption("Ключ используется только при нажатии кнопки. В Git и CSV он не сохраняется.")
        entered_key = st.text_input("OpenAI API key", type="password", key="openai_api_key_input")
    api_key = entered_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.caption("Введите ключ в блоке выше либо задайте OPENAI_API_KEY перед запуском. Основной анализ доступен без API.")
    elif st.button("Сформировать справку", type="primary"):
        with st.spinner("Готовлю справку по наблюдаемым фактам…"):
            try:
                facts = investigation_facts(selected, row, related, path)
                st.session_state["case_note"] = (selected, generate_case_note(facts, api_key))
            except Exception as exc:
                st.error(f"Не удалось получить AI-справку: {type(exc).__name__}. Проверьте ключ, модель и доступ к API.")
    if st.session_state.get("case_note", (None, None))[0] == selected:
        st.markdown(st.session_state["case_note"][1])

elif section == "Приоритеты":
    st.markdown('<div class="eyebrow">ШАГ 1 / ВЫБРАТЬ КАНДИДАТА</div>', unsafe_allow_html=True)
    st.title("Кого проверять первым")
    st.caption("Очередь из 50 ранее неизвестных узлов, отсортированных по значимости для ручной проверки.")
    selected_top = st.selectbox(
        "Быстрый переход к узлу",
        options=top.gid.astype(int).tolist(),
        format_func=lambda gid: f"gid {gid} · {ROLE_NAMES[roles.at[gid, 'role']]} · {roles.at[gid, 'priority_score']:.3f}",
    )
    if st.button("Посмотреть связи и основания →", type="primary"):
        open_gid(selected_top)
    st.markdown('<div class="small-note">Приоритет — порядок просмотра, а не оценка виновности. Основание для каждого места в рейтинге приведено в последнем столбце.</div>', unsafe_allow_html=True)
    top_view = top.copy()
    top_view["gid"] = top_view.gid.astype(str)
    top_view["роль"] = top_view.role.map(ROLE_NAMES)
    st.dataframe(
        top_view[["rank", "gid", "роль", "priority_score", "why"]].rename(columns={
            "rank": "№", "priority_score": "приоритет", "why": "обоснование",
        }),
        hide_index=True, width="stretch", height=700,
    )
    st.download_button("Скачать top_nodes.csv", (OUT / "top_nodes.csv").read_bytes(), "top_nodes.csv", "text/csv")

elif section == "Кластеры":
    st.markdown('<div class="eyebrow">СТРУКТУРА / ГРУППЫ СВЯЗЕЙ</div>', unsafe_allow_html=True)
    st.title("Кластеры сети")
    st.caption("Кластеры выделены методом Louvain по неориентированной проекции; роли и пути рассчитаны на направленном графе.")
    st.dataframe(clusters.rename(columns={
        "cluster_id": "кластер", "n_nodes": "узлов", "n_seed": "известных seed",
        "sum_kzt_internal": "внутренний оборот ₸", "top_gids": "ведущие gid",
        "hypothesis": "гипотеза",
    }), hide_index=True, width="stretch", height=650)
    col1, col2 = st.columns(2)
    col1.download_button("Скачать clusters.csv", (OUT / "clusters.csv").read_bytes(), "clusters.csv", "text/csv")
    col2.download_button("Скачать nodes_roles.csv", (OUT / "nodes_roles.csv").read_bytes(), "nodes_roles.csv", "text/csv")

else:
    st.markdown('<div class="eyebrow">ПРОЗРАЧНОСТЬ / ГРАНИЦЫ ДАННЫХ</div>', unsafe_allow_html=True)
    st.title("Как работает оценка")
    st.markdown("""
    Все роли присваиваются по проверяемым численным правилам. `role_score` показывает силу совпадения с правилом, а не вероятность причастности к преступлению. `priority_score` нужен для очередности ручной проверки.

    - **Координатор:** минимум два входа и выхода, достижим минимум из двух seed, высокая посредническая центральность.
    - **Консолидация:** минимум три плательщика, существенный объём входа и удержание минимум 35% внутри наблюдаемого графа.
    - **Распределитель:** отправляет минимум пяти получателям, входящих источников относительно мало.
    - **Транзит:** есть вход и выход; отношение исходящего объёма к входящему от 0.65 до 1.5. Время следующего выхода показывается отдельно.
    - **Конечный получатель:** вход есть, выхода не видно, а узел обнаружен раньше четвёртого колена.
    - **Периферия:** признаки выше не сработали, включая неизвестный статус узлов четвёртого колена.

    Приоритет складывается из центральности (25%), оборота (22%), числа достижимых seed (20%), числа связей (18%) и типа роли (15%). Уже известные seed и обрезанные листья получают понижающий коэффициент.

    **Границы данных:** только исходящие внутрибанковские переводы от 81 seed, четыре колена, порог 5 000 ₸, один месяц. Поэтому «удержание» означает разницу входа и выхода только *внутри выгрузки*. Временное совпадение входа и выхода также не доказывает, что это одни и те же деньги.
    """)
    st.download_button("Скачать все роли", (OUT / "nodes_roles.csv").read_bytes(), "nodes_roles.csv", "text/csv")

st.divider()
st.caption("MoneyMap · гипотезы для углублённой AML-проверки · данные обезличены")
