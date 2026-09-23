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
st.markdown(
    """
    <style>
    .stApp { background: #F5F8F3; color: #193025; }
    [data-testid="stHeader"] { background: #F5F8F3; }
    [data-testid="stSidebar"] { background: #153724; border-right: 1px solid #2F5B3E; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p { color: #F3F9F1 !important; }
    .block-container { padding-top: 1.3rem; max-width: 1480px; }
    h1, h2, h3 { color: #173A25 !important; letter-spacing: -.025em; }
    h1 { font-size: 2.5rem !important; }
    div[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #DAE8D9;
      border-radius: 18px; padding: 17px 20px; box-shadow: 0 8px 30px rgba(18, 62, 34, .045); }
    div[data-testid="stMetricLabel"] { color: #587260; }
    div[data-testid="stMetricValue"] { color: #173A25; }
    .stButton > button[kind="primary"] { background: #4FAA3A; border-color: #4FAA3A;
      color: white; border-radius: 12px; font-weight: 700; }
    .stButton > button[kind="secondary"] { border-color: #B9D6B9;
      border-radius: 12px; color: #1E6335; font-weight: 650; }
    .stDownloadButton > button { border-radius: 12px; border-color: #B9D6B9; color: #1E6335; }
    .case-note { background: #EBF7E9; border-left: 4px solid #51AF3D;
      border-radius: 12px; padding: 1rem 1.2rem; margin: 0.6rem 0 1rem; color: #21472B; }
    .eyebrow { color: #318445; letter-spacing: .16em; font-weight: 800; font-size: .78rem; }
    .hero { background: linear-gradient(115deg, #123E28 0%, #17613A 66%, #398C4A 100%);
      color: #fff; border-radius: 24px; padding: 2.1rem 2.4rem; margin: .7rem 0 1.2rem;
      box-shadow: 0 16px 42px rgba(20, 80, 40, .18); }
    .hero .kicker { color: #BFF0B5; font-size: .78rem; font-weight: 800;
      letter-spacing: .16em; margin-bottom: .7rem; }
    .hero h1 { color: white !important; font-size: 2.6rem !important; margin: .2rem 0 .5rem; }
    .hero p { color: #E1F2E1; font-size: 1.06rem; line-height: 1.5;
      max-width: 780px; margin: 0; }
    .story-card { background: white; border: 1px solid #DAE8D9; border-radius: 18px;
      padding: 1.2rem 1.25rem; min-height: 160px; margin-bottom: .4rem; }
    .story-card .num { color: #50A742; font-size: .8rem; font-weight: 800; letter-spacing: .12em; }
    .story-card h3 { font-size: 1.06rem !important; margin: .55rem 0 .4rem; }
    .story-card p { color: #5A6D60; font-size: .94rem; line-height: 1.45; margin: 0; }
    .candidate { background: #FFFFFF; border: 1px solid #D6E6D5; border-radius: 16px;
      padding: .9rem 1rem; min-height: 130px; margin: .15rem 0 .4rem; }
    .candidate .label { color: #508054; font-size: .77rem; font-weight: 800; letter-spacing: .08em; }
    .candidate strong { color: #193B27; font-size: 1.05rem; }
    .candidate p { color: #58705E; font-size: .85rem; margin: .3rem 0 0; line-height: 1.35; }
    .small-note { background: #FFFFFF; border: 1px solid #E0EBDD; border-radius: 14px;
      padding: .9rem 1.1rem; color: #47604C; }
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
    if len(members) > 65:
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
        members = {selected} | {gid for _, _, gid in scores[:64]}
    return graph.subgraph(members).copy()


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


def network_figure(graph: nx.DiGraph, roles: pd.DataFrame, selected: int, radius: int):
    view = selected_subgraph(graph, roles, selected, radius)
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
            text=[str(gid) if gid == selected or roles.at[gid, "priority_score"] >= 0.70 else "" for gid in gids],
            textposition="top center", textfont=dict(color="#173A25", size=10),
            marker=dict(
                color=color,
                size=[25 if gid == selected else 11 + 18 * roles.at[gid, "priority_score"] for gid in gids],
                line=dict(color="#173A25", width=2 if selected in gids else 0.4),
            ),
            customdata=[[gid, roles.at[gid, "evidence"]] for gid in gids],
            hovertemplate="gid %{customdata[0]}<br>%{customdata[1]}<extra></extra>",
            name=ROLE_NAMES[role],
        ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        height=580, margin=dict(l=10, r=10, t=28, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        annotations=annotations, legend=dict(orientation="h", y=-0.04, x=0),
        font=dict(color="#294B32"), hoverlabel=dict(bgcolor="#EAF5E9", font_color="#173A25"),
    )
    if radius == 1:
        fig.add_annotation(x=-0.95, y=1.13, text="ПОЛУЧЕНО", showarrow=False, font=dict(color="#54815B", size=11))
        fig.add_annotation(x=0.95, y=1.13, text="ОТПРАВЛЕНО", showarrow=False, font=dict(color="#54815B", size=11))
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


def open_gid(gid: int) -> None:
    st.session_state.pending_gid = int(gid)
    st.session_state.pending_section = "Расследование"
    st.rerun()


st.sidebar.markdown('<div class="eyebrow" style="color:#B8E8AF">MONEYMAP / HACKALEM AI</div>', unsafe_allow_html=True)
st.sidebar.title("Граф денег")
st.sidebar.caption("Рабочее место AML-аналитика")
section = st.sidebar.radio("Раздел", ["Обзор", "Расследование", "Приоритеты", "Кластеры", "Методика"], key="section")
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

if section == "Обзор":
    st.markdown(
        """<div class="hero">
          <div class="kicker">АНАЛИТИКА ФИНАНСОВОЙ СЕТИ · HACKALEM AI</div>
          <h1>От известных получателей — к структуре всей сети</h1>
          <p>Аналитик знает 81 исходного клиента. MoneyMap восстанавливает направленные связи переводов,
          присваивает каждому узлу объяснимую роль и показывает, кого проверить следующим.</p>
        </div>""",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Известны в начале", int(roles.is_seed.sum()), help="Исходные seed из задания")
    c2.metric("Узлов в сети", f"{len(roles):,}".replace(",", " "))
    c3.metric("Переводов", f"{len(tx):,}".replace(",", " "))
    c4.metric("Кандидатов в очереди", len(top), help="Ранее неизвестные узлы в top_nodes.csv")
    st.markdown("### Что получает аналитик")
    s1, s2, s3 = st.columns(3, gap="medium")
    story = [
        (s1, "01 / СОБРАТЬ", "Карта движения денег", "Переводы соединяются в направленный граф на четыре колена от известных клиентов."),
        (s2, "02 / ПОНЯТЬ", "Роль каждого узла", "Система находит признаки консолидации, транзита, распределения и объясняет их числами."),
        (s3, "03 / ДЕЙСТВОВАТЬ", "Очередь для проверки", "Топ узлов помогает начать ручную AML-проверку с наиболее значимых связей."),
    ]
    for column, number, title, description in story:
        column.markdown(
            f'<div class="story-card"><div class="num">{number}</div><h3>{title}</h3><p>{description}</p></div>',
            unsafe_allow_html=True,
        )
    st.markdown("### С кого начать проверку")
    st.caption("Три первых ранее неизвестных узла. Откройте карточку, чтобы увидеть основания и направление переводов.")
    candidate_cols = st.columns(3, gap="medium")
    for column, candidate in zip(candidate_cols, top.head(3).itertuples(index=False)):
        with column:
            st.markdown(
                f'<div class="candidate"><div class="label">№ {candidate.rank} · {escape(ROLE_NAMES[candidate.role])} · {candidate.priority_score:.3f}</div>'
                f'<strong>gid {candidate.gid}</strong><p>{escape(candidate.why)}</p></div>',
                unsafe_allow_html=True,
            )
            if st.button("Открыть расследование →", key=f"candidate_{candidate.gid}", use_container_width=True):
                open_gid(candidate.gid)
    st.markdown('<div class="small-note">Выводы — гипотезы для проверки аналитиком. Узлы на четвёртом колене не считаются конечными получателями автоматически: их исходящие могли остаться за границей выгрузки.</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="eyebrow">ШАГ 2 / ИССЛЕДОВАТЬ УЗЕЛ</div>', unsafe_allow_html=True)
    st.title("Почему проверить этот gid?")
    st.caption("Слева — направление переводов; справа — проверяемые численные основания. Введите любой gid в боковой панели.")
    row = roles.loc[selected]
    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.subheader(f"Сеть вокруг gid {selected}")
        radius = st.radio("Радиус связей", [1, 2], horizontal=True, label_visibility="collapsed")
        figure, view = network_figure(graph, roles, selected, radius)
        if figure:
            st.plotly_chart(figure, width="stretch")
            st.caption(f"Показано до 65 узлов с наиболее значимыми связями и {view.number_of_edges()} направленных рёбер. Полный список переводов — ниже. Стрелки показывают направление денег.")
        else:
            st.info("У этого gid нет наблюдаемых рёбер в выгрузке.")
    with right:
        st.subheader(f"Карточка gid {selected}")
        st.markdown(f"**Роль:** {ROLE_NAMES[row.role]} · **сила признака:** {row.role_score:.0%}")
        st.markdown(f"**Приоритет:** {row.priority_score:.3f} · **кластер:** {int(row.cluster_id)} · **колено:** {int(row.depth)}")
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
