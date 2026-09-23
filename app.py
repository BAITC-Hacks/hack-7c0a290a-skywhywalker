"""MoneyMap investigation UI. Start with: streamlit run app.py"""

from __future__ import annotations

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
    "coordinator": "#f97373",
    "consolidator": "#f7b955",
    "distributor": "#b58cff",
    "transit": "#55c9d7",
    "terminal": "#7dd3a4",
    "peripheral": "#8291ab",
}


st.set_page_config(page_title="MoneyMap · AML аналитика", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #0b1220; color: #eef3fa; }
    [data-testid="stSidebar"] { background: #111d2e; }
    .block-container { padding-top: 1.7rem; max-width: 1500px; }
    h1, h2, h3 { color: #eef3fa !important; }
    div[data-testid="stMetric"] { background: #152238; border: 1px solid #273954;
      border-radius: 14px; padding: 15px 18px; }
    div[data-testid="stMetricLabel"] { color: #a5b4ca; }
    .case-note { background: #152238; border-left: 4px solid #4dc6d5;
      border-radius: 8px; padding: 1rem 1.2rem; margin: 0.6rem 0 1rem; }
    .eyebrow { color: #55c9d7; letter-spacing: .16em; font-weight: 700; font-size: .8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


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


def selected_subgraph(graph: nx.DiGraph, roles: pd.DataFrame, selected: int, radius: int):
    neighbors = nx.single_source_shortest_path_length(graph.to_undirected(), selected, cutoff=radius)
    members = set(neighbors)
    if len(members) > 105:
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
        members = {selected} | {gid for _, _, gid in scores[:104]}
    return graph.subgraph(members).copy()


def network_figure(graph: nx.DiGraph, roles: pd.DataFrame, selected: int, radius: int):
    view = selected_subgraph(graph, roles, selected, radius)
    if view.number_of_nodes() == 1:
        return None, view
    positions = nx.spring_layout(view.to_undirected(), seed=17, weight=None, iterations=90)
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
            arrowwidth=1.3, arrowcolor="#7f91aa", text="",
        ))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines", line=dict(width=1.2, color="#53647c"),
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
            text=[str(gid) if gid == selected or roles.at[gid, "priority_score"] >= 0.70 else "" for gid in gids],
            textposition="top center", textfont=dict(color="#e9f0f8", size=10),
            marker=dict(
                color=color,
                size=[25 if gid == selected else 11 + 18 * roles.at[gid, "priority_score"] for gid in gids],
                line=dict(color="#f3f7ff", width=2 if selected in gids else 0.4),
            ),
            customdata=[[gid, roles.at[gid, "evidence"]] for gid in gids],
            hovertemplate="gid %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
            name=ROLE_NAMES[role],
        ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#111d2e", plot_bgcolor="#111d2e",
        height=580, margin=dict(l=10, r=10, t=15, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=annotations, legend=dict(orientation="h", y=-0.04, x=0),
        hoverlabel=dict(bgcolor="#1b2a43"),
    )
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

st.sidebar.markdown('<div class="eyebrow">MONEYMAP / HACKALEM AI</div>', unsafe_allow_html=True)
st.sidebar.title("Навигация")
section = st.sidebar.radio("Раздел", ["Расследование", "Приоритеты", "Кластеры", "Методика"])
st.sidebar.divider()
default_gid = int(top.iloc[0].gid)
gid_text = st.sidebar.text_input("Найти gid", value=str(default_gid))
if not gid_text.isdigit() or int(gid_text) not in roles.index:
    st.sidebar.error("Укажите gid из набора данных")
    selected = default_gid
else:
    selected = int(gid_text)

st.markdown('<div class="eyebrow">EXPLAINABLE AML INVESTIGATION</div>', unsafe_allow_html=True)
st.title("Граф денег")
st.caption("Четыре колена переводов · июль 2026 · внутрибанковская сеть")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Узлов", f"{len(roles):,}".replace(",", " "))
c2.metric("Связей", f"{len(edges):,}".replace(",", " "))
c3.metric("Исходных seed", int(roles.is_seed.sum()))
c4.metric("Кластеров", len(clusters))
st.divider()

if section == "Расследование":
    row = roles.loc[selected]
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.subheader(f"Сеть вокруг gid {selected}")
        radius = st.radio("Радиус связей", [1, 2], horizontal=True, label_visibility="collapsed")
        figure, view = network_figure(graph, roles, selected, radius)
        if figure:
            st.plotly_chart(figure, width="stretch")
            st.caption(f"Показано {len(view)} узлов и {view.number_of_edges()} направленных связей. Стрелки показывают направление денег.")
        else:
            st.info("У этого gid нет наблюдаемых рёбер в выгрузке.")
    with right:
        st.subheader(f"Карточка gid {selected}")
        st.markdown(f"**Роль:** {ROLE_NAMES[row.role]} · **уверенность:** {row.role_score:.0%}")
        st.markdown(f"**Приоритет:** {row.priority_score:.3f} · **кластер:** {int(row.cluster_id)} · **колено:** {int(row.depth)}")
        st.markdown(f'<div class="case-note">{row.evidence}</div>', unsafe_allow_html=True)
        m1, m2 = st.columns(2)
        m1.metric("Получено в графе", fmt_kzt(row.in_kzt))
        m2.metric("Отправлено в графе", fmt_kzt(row.out_kzt))
        m3, m4 = st.columns(2)
        m3.metric("Плательщиков", int(row.in_deg))
        m4.metric("Получателей", int(row.out_deg))
        st.write(f"Достижим из **{int(row.seed_reach)}** исходных seed; доля быстрых выходов после поступления — **{row.fast_forward:.0%}**.")
        path = shortest_seed_path(graph, roles, selected)
        if path:
            st.write("Кратчайший наблюдаемый путь от seed: **" + " → ".join(map(str, path)) + "**")
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
    st.dataframe(
        related[["направление", "src", "dst", "sum_kzt", "n_tx", "depth"]].rename(columns={
            "src": "плательщик", "dst": "получатель", "sum_kzt": "сумма ₸",
            "n_tx": "транзакций", "depth": "колено",
        }),
        hide_index=True, width="stretch", height=280,
    )

elif section == "Приоритеты":
    st.subheader("Кого проверить первым")
    st.caption("Рейтинг включает неизвестные ранее узлы. Выбор gid в боковой панели открывает его карточку в разделе «Расследование».")
    top_view = top.copy()
    top_view["роль"] = top_view.role.map(ROLE_NAMES)
    st.dataframe(
        top_view[["rank", "gid", "роль", "priority_score", "why"]].rename(columns={
            "rank": "№", "priority_score": "приоритет", "why": "обоснование",
        }),
        hide_index=True, width="stretch", height=700,
    )
    st.download_button("Скачать top_nodes.csv", (OUT / "top_nodes.csv").read_bytes(), "top_nodes.csv", "text/csv")

elif section == "Кластеры":
    st.subheader("Структура сети")
    st.caption("Кластеры выделены методом Louvain по неориентированной проекции; роли и пути рассчитаны на направленном графе.")
    st.dataframe(clusters, hide_index=True, width="stretch", height=650)
    col1, col2 = st.columns(2)
    col1.download_button("Скачать clusters.csv", (OUT / "clusters.csv").read_bytes(), "clusters.csv", "text/csv")
    col2.download_button("Скачать nodes_roles.csv", (OUT / "nodes_roles.csv").read_bytes(), "nodes_roles.csv", "text/csv")

else:
    st.subheader("Как читать выводы")
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
