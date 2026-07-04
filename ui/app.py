"""UI «Научного клубка»: чат + аналитика + граф + пробелы.
Дизайн — по финальному мокапу DGC (standalone.html, 28.06).
Запуск: streamlit run ui/app.py
"""
from __future__ import annotations

import os
import re
import urllib.parse

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")


# API — внутренний адрес для запросов Streamlit -> FastAPI (сервер к серверу,
# всегда localhost, т.к. они на одной машине). PUBLIC_API — адрес, по которому
# сможет достучаться БРАУЗЕР пользователя (ссылки на скачивание файлов). Если
# не задан отдельно, публичного доступа к файлам не будет — задай его в .env
# или при запуске: PUBLIC_API_URL=http://<IP-или-домен>:8000 streamlit run ...
PUBLIC_API = os.environ.get("PUBLIC_API_URL", API)


def _file_url(path: str) -> str:
    return f"{PUBLIC_API}/files/{urllib.parse.quote(path)}"


def _safe_get(url: str, **kwargs):
    """GET с понятной ошибкой вместо трейсбека — если бэкенд не обновлён
    (эндпоинта ещё нет) или недоступен."""
    try:
        resp = requests.get(url, **kwargs)
    except Exception as e:
        return None, f"Не удалось подключиться к API: {e}"
    if not resp.ok:
        return None, (
            f"API вернул ошибку {resp.status_code} на {url}. "
            "Возможно, сервер запущен со старой версией кода — перезапустите API."
        )
    try:
        return resp.json(), None
    except ValueError:
        return None, "API вернул не-JSON ответ."


def _build_doc_links(rows: list[dict], chunks: list[dict]) -> dict[str, str]:
    """doc_id -> относительный путь файла, из фактов графа и векторных чанков."""
    links: dict[str, str] = {}
    for row in rows:
        for d in (row.get("documents") or []):
            if isinstance(d, dict) and d.get("id") and d.get("path"):
                links[d["id"]] = d["path"]
    for c in chunks:
        if c.get("doc_id") and c.get("source_path"):
            links.setdefault(c["doc_id"], c["source_path"])
    return links


def _linkify_citations(text: str, doc_links: dict[str, str]) -> str:
    """[doc-id] в тексте ответа -> кликабельная markdown-ссылка на файл, если путь известен."""
    def repl(m: re.Match) -> str:
        doc_id = m.group(1)
        path = doc_links.get(doc_id)
        return f"[{doc_id}]({_file_url(path)})" if path else m.group(0)
    return re.sub(r"\[([\w\-]+)\]", repl, text)


def _verification_badge(rows: list[dict]) -> str | None:
    """Считает источники/дату актуализации напрямую из фактов — не зависит
    от того, упомянула ли модель это в тексте ответа."""
    doc_ids: set[str] = set()
    dates: list[str] = []
    for r in rows:
        for d in (r.get("documents") or []):
            if isinstance(d, dict):
                if d.get("id"):
                    doc_ids.add(d["id"])
                if d.get("loaded_at"):
                    dates.append(str(d["loaded_at"]))
        if r.get("actualized_at"):
            dates.append(str(r["actualized_at"]))
    parts = []
    if doc_ids:
        parts.append(f"Источников: {len(doc_ids)}")
    if dates:
        parts.append(f"Актуально на: {max(dates)[:10]}")
    if not parts:
        return None
    return (
        '<div style="display:inline-flex;gap:10px;background:#eef6fd;border:1px solid #9fd8f7;'
        'border-radius:20px;padding:4px 14px;font-size:12px;color:#004c97;margin:8px 0;">'
        + " &nbsp;·&nbsp; ".join(parts) + "</div>"
    )

st.set_page_config(
    page_title="Научный клубок — Норникель",
    layout="wide",
    page_icon="🧶",
    menu_items={"About": "Nornickel AI Science Hack · Трек 02 «Научный клубок»"},
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Onest', -apple-system, sans-serif; }
.stApp { background-color: #eff7fa; }
header[data-testid="stHeader"] { background: #0079c2; height: 0; }
h1, h2, h3 { color: #162c3e !important; font-weight: 500 !important; }
[data-testid="stTabs"] [role="tablist"] {
    background: #fff; border-bottom: 1px solid #d6dfe4; padding: 0 8px;
}
[data-testid="stTabs"] [role="tab"] {
    color: #697f8b; font-weight: 400; font-size: 14px; height: 48px;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #0079c2 !important; font-weight: 600;
    border-bottom: 2px solid #0079c2 !important;
}
.stButton > button {
    background-color: #0079c2 !important; color: #fff !important;
    border: none !important; border-radius: 6px !important;
    font-weight: 500 !important; font-family: 'Onest', sans-serif !important;
}
.stButton > button:hover { background-color: #004c97 !important; }
div[data-testid="column"] .stButton > button {
    background-color: #fff !important; color: #162c3e !important;
    border: 1.5px solid #0079c2 !important; border-radius: 8px !important;
    font-weight: 400 !important; font-size: 13px !important;
    text-align: left !important; white-space: normal !important; height: auto !important;
    line-height: 1.45 !important;
}
div[data-testid="column"] .stButton > button:hover { background-color: #eff7fa !important; }
[data-testid="stChatInput"] { border: 1.5px solid #d6dfe4; border-radius: 10px; background: #fff; }
[data-testid="stChatInput"] textarea { font-family: 'Onest', sans-serif !important; }
[data-testid^="stChatMessageAvatar"] { display: none; }
[data-testid="stChatMessage"] {
    background: #fff; border: 1px solid #d6dfe4; border-radius: 10px 10px 10px 3px;
    box-shadow: 0 1px 3px rgba(22,44,62,.06); padding: 10px 14px;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #0079c2; border: none; border-radius: 10px 10px 3px 10px;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p { color: #fff; }
[data-testid="stExpander"] {
    background: #fff; border: 1px solid #d6dfe4 !important; border-radius: 10px !important;
    box-shadow: 0 1px 3px rgba(22,44,62,.06);
}
[data-testid="stExpander"] summary { color: #162c3e !important; font-weight: 500; }
[data-testid="stTextInput"] input {
    border: 1.5px solid #d6dfe4 !important; border-radius: 6px !important;
    font-family: 'Onest', sans-serif !important; color: #162c3e;
}
[data-testid="stCaptionContainer"] { color: #6b7984 !important; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: #d6dfe4; border-radius: 3px; }
.nn-header {
    display: flex; align-items: center; gap: 20px;
    background: #0079c2; height: 64px; padding: 0 32px;
    border-radius: 0 0 8px 8px; margin: -1rem -1rem 8px -1rem;
    box-shadow: 0 2px 8px rgba(22,44,62,.18);
}
.nn-header-title { color: #fff; font-size: 16px; font-weight: 500; margin: 0; line-height: 1.2; }
.nn-header-sub { color: rgba(255,255,255,.65); font-size: 11px; margin: 2px 0 0 0; }
.nn-badge {
    background: rgba(255,255,255,.15); color: #fff;
    padding: 4px 12px; border-radius: 20px; font-size: 11px; white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="nn-header">
  <div>
    <p class="nn-header-title">Научный клубок — Норникель</p>
    <p class="nn-header-sub">Knowledge Graph · Материалы · Эксперименты · Режимы · Свойства</p>
  </div>
  <div style="margin-left:auto">
    <span class="nn-badge">Nornickel AI Science Hack · Трек 02</span>
  </div>
</div>
""", unsafe_allow_html=True)

tab_chat, tab_stats, tab_graph, tab_gaps, tab_library = st.tabs(
    ["Поиск по знаниям", "Аналитика", "Граф связей", "Пробелы в данных", "Библиотека документов"]
)

# ---------------- Чат ----------------
with tab_chat:
    if "history" not in st.session_state:
        st.session_state.history = []

    st.markdown("##### Примеры вопросов")
    examples = [
        "Какие технические решения циркуляции католита при электроэкстракции никеля описаны в практике?",
        "Какие методы обессоливания воды подходят при сульфатах 200–300 мг/л?",
        "Что известно о распределении Au, Ag и МПГ между штейном и шлаком?",
        "Где в данных есть противоречия?",
    ]
    row1 = st.columns(2)
    row2 = st.columns(2)
    for c, ex in zip(row1 + row2, examples):
        if c.button(ex, use_container_width=True):
            st.session_state.pending = ex

    GEO_OPTIONS = {"Любая": None, "Отечественная практика (РФ)": "РФ", "Зарубежная практика": "зарубеж"}
    geo_choice = st.selectbox("Географический фильтр", list(GEO_OPTIONS.keys()), index=0)

    with st.expander("Точный поиск по числовому условию"):
        st.caption(
            "Прямое сравнение диапазонов по графу условий — без интерпретации ИИ "
            "(концентрации, температуры, скорости потока, экономические показатели)."
        )
        cn, cn_err = _safe_get(f"{API}/condition-names", timeout=30)
        if cn_err:
            st.warning(cn_err)
            cn = []
        if cn:
            labels = [f"{c['name']} ({c.get('unit') or 'без единиц'}, {c['n']})" for c in cn]
            name_by_label = {lbl: c["name"] for lbl, c in zip(labels, cn)}
            unit_by_label = {lbl: c.get("unit") for lbl, c in zip(labels, cn)}
            csel1, csel2, csel3, csel4 = st.columns([2, 1, 1, 1])
            with csel1:
                sel_label = st.selectbox("Параметр", labels)
            with csel2:
                op = st.selectbox("Условие", ["<=", ">=", "range"])
            with csel3:
                val = st.number_input("Значение", value=0.0, step=1.0)
            with csel4:
                val_max = st.number_input("До (для диапазона)", value=0.0, step=1.0) if op == "range" else None
            if st.button("Найти по условию"):
                params = {"name": name_by_label[sel_label], "operator": op, "value": val}
                if unit_by_label.get(sel_label):
                    params["unit"] = unit_by_label[sel_label]
                if val_max:
                    params["value_max"] = val_max
                with st.spinner("Сравниваю диапазоны..."):
                    res, res_err = _safe_get(f"{API}/conditions", params=params, timeout=30)
                if res_err:
                    st.warning(res_err)
                elif not res:
                    st.info("Совпадений не найдено.")
                else:
                    st.dataframe(pd.DataFrame(res), use_container_width=True)
        else:
            st.caption("Список условий пуст — граф ещё не загружен.")

    st.divider()

    q = st.chat_input("Например: что делали по материалу X при процессе Y и какой эффект на показатель Z")
    q = q or st.session_state.pop("pending", None)

    for role, content in st.session_state.history:
        st.chat_message(role).write(content)

    if q:
        st.chat_message("user").write(q)
        st.session_state.history.append(("user", q))
        with st.spinner("Распутываю клубок..."):
            r = requests.post(
                f"{API}/ask",
                json={"question": q, "geography": GEO_OPTIONS[geo_choice]},
                timeout=120,
            ).json()
        doc_links = _build_doc_links(r.get("facts", []), r.get("chunks", []))
        with st.chat_message("assistant"):
            st.markdown(_linkify_citations(r["answer"], doc_links))
            badge = _verification_badge(r.get("facts", []))
            if badge:
                st.markdown(badge, unsafe_allow_html=True)
            if r.get("facts"):
                with st.expander(f"Факты из графа ({len(r['facts'])})"):
                    facts_df = pd.DataFrame(r["facts"])
                    st.dataframe(facts_df, use_container_width=True)
            if r.get("numeric_matches"):
                with st.expander(
                    f"Числовые условия, сопоставленные с запросом ({len(r['numeric_matches'])})"
                ):
                    st.caption(
                        "Пересечение диапазонов из вопроса и из графа — эвристика, "
                        "не инженерное заключение. Решение проверяйте по первоисточнику."
                    )
                    st.dataframe(pd.DataFrame(r["numeric_matches"]), use_container_width=True)
            if r.get("experts"):
                with st.expander(f"Эксперты и лаборатории по теме ({len(r['experts'])})"):
                    st.dataframe(
                        pd.DataFrame(r["experts"]).rename(
                            columns={"person": "Эксперт", "role": "Роль", "lab": "Лаборатория"}
                        ),
                        use_container_width=True, hide_index=True,
                    )
            if r.get("chunks"):
                with st.expander("Источники (фрагменты документов)"):
                    for c in r["chunks"]:
                        path = c.get("source_path")
                        title = f"[{c.get('doc_id')}]({_file_url(path)})" if path else c.get("doc_id")
                        st.markdown(f"**{title}** · `{path}` · score {c.get('score'):.2f}")
                        st.text(c.get("text", "")[:500])
            if r.get("focus_entity"):
                st.caption(f"Сущность в фокусе: `{r['focus_entity']}` — смотри вкладку «Граф связей»")

            md_lines = [f"# Запрос: {q}", "", r["answer"], ""]
            if r.get("facts"):
                md_lines.append("## Факты из графа")
                for f in r["facts"]:
                    md_lines.append(f"- {f}")
                md_lines.append("")
            if r.get("numeric_matches"):
                md_lines.append("## Числовые условия")
                for nm in r["numeric_matches"]:
                    verdict = "подходит" if nm.get("fits") else "не подходит"
                    md_lines.append(f"- {nm.get('name')}: {nm.get('raw')} ({verdict})")
                md_lines.append("")
            if r.get("experts"):
                md_lines.append("## Эксперты и лаборатории")
                for ex in r["experts"]:
                    md_lines.append(f"- {ex.get('person')} ({ex.get('role') or '—'}) · {ex.get('lab') or '—'}")
                md_lines.append("")
            if r.get("chunks"):
                md_lines.append("## Источники")
                for c in r["chunks"]:
                    md_lines.append(f"- **{c.get('doc_id')}** · `{c.get('source_path')}`")
            report_md = "\n".join(md_lines)

            col_a, col_b = st.columns(2)
            with col_a:
                st.download_button(
                    "Экспорт ответа (Markdown)", data=report_md,
                    file_name="otvet.md", mime="text/markdown",
                    use_container_width=True,
                )
            with col_b:
                if r.get("facts"):
                    st.download_button(
                        "Экспорт фактов (CSV)", data=pd.DataFrame(r["facts"]).to_csv(index=False),
                        file_name="fakty.csv", mime="text/csv",
                        use_container_width=True,
                    )
        st.session_state.history.append(("assistant", r["answer"]))

# ---------------- Аналитика ----------------
with tab_stats:
    st.markdown("##### Обзор базы знаний")
    if st.button("Обновить метрики"):
        with st.spinner("Считаю..."):
            s = requests.get(f"{API}/stats", timeout=60).json()
        counts = {r["label"]: r["n"] for r in s["nodes"]}
        cards = [
            ("Документов", counts.get("Document", 0), True),
            ("Материалов", counts.get("Material", 0), False),
            ("Выводов", counts.get("Finding", 0), False),
            ("Условий", counts.get("Condition", 0), False),
            ("Экспертов", counts.get("Person", 0), False),
            ("Связей", s["relations"], False),
        ]
        card_html = '<div style="display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap;">'
        for label, value, filled in cards:
            bg = "#0079c2" if filled else "#fff"
            vc = "#fff" if filled else "#0079c2"
            lc = "rgba(255,255,255,.7)" if filled else "#6b7984"
            card_html += (
                f'<div style="background:{bg};border-radius:10px;padding:18px 20px;flex:1;'
                f'min-width:120px;box-shadow:0 1px 3px rgba(22,44,62,.08);">'
                f'<div style="font-size:36px;font-weight:300;color:{vc};line-height:1;">{value}</div>'
                f'<div style="font-size:12px;color:{lc};margin-top:6px;">{label}</div></div>'
            )
        card_html += "</div>"
        st.markdown(card_html, unsafe_allow_html=True)

        import plotly.express as px

        PLOT_STYLE = dict(
            paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
            font=dict(family="Onest, Arial, sans-serif", color="#162c3e"),
            margin=dict(l=10, r=10, t=40, b=10),
        )
        col1, col2 = st.columns(2)
        with col1:
            df = pd.DataFrame(s["top_materials"])
            if not df.empty:
                fig = px.bar(df, x="n", y="name", orientation="h",
                             labels={"n": "исследований", "name": ""})
                fig.update_traces(marker_color="#0079c2", marker_line_width=0)
                fig.update_layout(title="Охват по материалам", height=320,
                                  yaxis=dict(autorange="reversed"), **PLOT_STYLE)
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            df = pd.DataFrame(s["docs_by_type"])
            if not df.empty:
                fig = px.pie(df, values="n", names="doc_type", hole=0.55)
                fig.update_traces(
                    marker=dict(colors=["#0079c2", "#2492DD", "#70CAF2", "#004c97", "#9fd8f7", "#d6dfe4"]),
                    textinfo="label+value", textfont=dict(family="Onest, Arial, sans-serif"),
                )
                fig.update_layout(title="Документы по типам", height=320,
                                  showlegend=False, **PLOT_STYLE)
                st.plotly_chart(fig, use_container_width=True)

        df = pd.DataFrame(s["docs_by_year"])
        if not df.empty:
            fig = px.bar(df, x="year", y="n", labels={"n": "документов", "year": "год"})
            fig.update_traces(marker_color="#0079c2", marker_line_width=0)
            fig.update_layout(title="Динамика по годам", height=280, **PLOT_STYLE)
            st.plotly_chart(fig, use_container_width=True)

        df = pd.DataFrame(s["top_labs"])
        if not df.empty:
            st.markdown("**Лаборатории — носители экспертизы** (по числу документов)")
            st.dataframe(
                df.rename(columns={"name": "Лаборатория", "n": "Документов"}),
                use_container_width=True, hide_index=True,
            )

        st.markdown("---")
        st.markdown("##### Дашборд для руководителя")

        col3, col4 = st.columns(2)
        with col3:
            df = pd.DataFrame(s.get("domains", []))
            if not df.empty:
                fig = px.bar(df, x="n", y="domain", orientation="h",
                             labels={"n": "документов", "domain": ""})
                fig.update_traces(marker_color="#0079c2", marker_line_width=0)
                fig.update_layout(title="Покрытие по направлениям", height=300,
                                  yaxis=dict(autorange="reversed"), **PLOT_STYLE)
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Направление определяется по ключевым словам в названии/тегах — "
                           "приближённая оценка, не поле онтологии.")
        with col4:
            df = pd.DataFrame(s.get("lab_activity", []))
            top_lab_names = set(pd.DataFrame(s["top_labs"])["name"].head(6)) if s.get("top_labs") else set()
            df = df[df["lab"].isin(top_lab_names)] if (not df.empty and top_lab_names) else df
            if not df.empty:
                fig = px.bar(df, x="year", y="n", color="lab", barmode="group",
                             labels={"n": "документов", "year": "год", "lab": "Лаборатория"},
                             color_discrete_sequence=["#0079c2", "#2492DD", "#70CAF2",
                                                       "#004c97", "#9fd8f7", "#1a3a5c"])
                fig.update_layout(title="Активность лабораторий по годам", height=300, **PLOT_STYLE)
                st.plotly_chart(fig, use_container_width=True)

        df = pd.DataFrame(s.get("risk_zones", []))
        if not df.empty:
            st.markdown("**Зоны риска** — темы с малым числом источников или противоречиями")
            st.dataframe(
                df.rename(columns={"material": "Материал", "property": "Показатель", "reason": "Причина"}),
                use_container_width=True, hide_index=True,
            )

    st.divider()
    st.markdown("**Аудит действий** — последние запросы к системе (кто, что, когда).")
    if st.button("Показать журнал"):
        with st.spinner("Читаю журнал..."):
            audit_rows, audit_err = _safe_get(f"{API}/audit", timeout=30)
        if audit_err:
            st.warning(audit_err)
        elif not audit_rows:
            st.info("Журнал пуст.")
        else:
            st.dataframe(
                pd.DataFrame(audit_rows).rename(columns={
                    "ts": "Время", "action": "Действие", "question": "Вопрос",
                    "geography": "География", "ip": "IP",
                }),
                use_container_width=True, hide_index=True,
            )

# ---------------- Граф ----------------
with tab_graph:
    # Навигация по узлам — через session_state и st.rerun(), НЕ через URL:
    # переход ссылкой (?entity_id=...) вызывает полную перезагрузку страницы
    # и сбрасывает Streamlit-вкладки на первую. Кнопки ниже переключают фокус
    # без перезагрузки — вкладка «Граф связей» остаётся открытой.
    if st.session_state.get("_pending_focus_id"):
        st.session_state["graph_focus_id"] = st.session_state.pop("_pending_focus_id")
        st.session_state["graph_shown"] = True
    st.session_state.setdefault("graph_focus_id", "mat-nikel")
    st.session_state.setdefault("graph_shown", False)

    col1, col2 = st.columns([3, 1])
    with col1:
        st.text_input("ID сущности", key="graph_focus_id",
                       placeholder="mat-nikel / prop-izvlechenie / exp-... ")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Показать граф", use_container_width=True):
            st.session_state["graph_shown"] = True
    entity_id = st.session_state["graph_focus_id"]

    st.caption(
        "Введите ID сущности из ответа в чате (поле «Сущность в фокусе») или из таблицы фактов — "
        "либо нажмите «Показать связи» у любого объекта в списке ниже, чтобы перейти к нему."
    )

    palette = {
        "Material":   "#004c97",
        "Property":   "#0079c2",
        "Mode":       "#70CAF2",
        "Condition":  "#9fd8f7",
        "Experiment": "#23c38f",
        "Finding":    "#2492DD",
        "Equipment":  "#697f8b",
        "Document":   "#6b7984",
        "Person":     "#ababac",
        "Lab":        "#162c3e",
        "Tag":        "#d6dfe4",
    }
    legend_items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin:3px 10px 3px 0;'
        f'font-size:12px;color:#162c3e;">'
        f'<span style="width:12px;height:12px;border-radius:50%;background:{c};display:inline-block"></span>'
        f'{lbl}</span>'
        for lbl, c in palette.items()
    )
    st.markdown(
        f'<div style="background:#fff;border:1px solid #d6dfe4;border-radius:8px;'
        f'padding:8px 16px;margin-bottom:12px;display:flex;flex-wrap:wrap;">{legend_items}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state["graph_shown"]:
        data = requests.get(f"{API}/subgraph/{entity_id}", timeout=60).json()
        if not data["nodes"]:
            st.warning("Пусто — проверь ID сущности.")
        else:
            from pyvis.network import Network

            try:
                contr = requests.get(f"{API}/contradictions", timeout=30).json()
            except Exception:
                contr = []
            contr_ids = {
                c[k] for c in contr for k in ("finding_a_id", "finding_b_id") if c.get(k)
            }

            net = Network(
                height="640px", width="100%",
                bgcolor="#f8fbfd", font_color="#162c3e",
                directed=True,
            )
            for n in data["nodes"]:
                is_focus = n["id"] == entity_id
                is_contr = n["id"] in contr_ids
                title = f"<b>{n['label']}</b><br>{n['name']}"
                if n.get("label") == "Document" and n.get("path"):
                    title += f'<br><a href="{_file_url(n["path"])}" target="_blank">Открыть / скачать</a>'
                if is_contr:
                    title = "<b>ПРОТИВОРЕЧИЕ</b><br>" + title
                net.add_node(
                    n["id"], label=n["name"], title=title,
                    color={
                        "background": "#dc2626" if is_contr else palette.get(n["label"], "#0079c2"),
                        "border": "#7f1d1d" if is_contr else "#ffffff",
                        "highlight": {"background": "#0079c2", "border": "#004c97"},
                    },
                    borderWidth=3 if is_contr else 2,
                    size=34 if is_focus else 20,
                    font={"color": "#162c3e", "size": 13, "face": "Onest, Arial"},
                )
            for e in data["edges"]:
                net.add_edge(
                    e["source"], e["target"], label=e["type"],
                    color={"color": "#d6dfe4", "highlight": "#0079c2"},
                    font={"size": 9, "color": "#6b7984"},
                )
            net.repulsion(node_distance=160, spring_length=180)
            net.save_graph("/tmp/knot_graph.html")
            st.components.v1.html(open("/tmp/knot_graph.html", encoding="utf-8").read(), height=660)
            if contr_ids & {n["id"] for n in data["nodes"]}:
                st.caption("Узлы с красной обводкой — выводы (Finding), участвующие в противоречиях.")

            st.markdown("##### Документы, связанные с этим узлом")
            docs_here = [n for n in data["nodes"]
                        if n["id"] != entity_id and n.get("label") == "Document" and n.get("path")]
            if not docs_here:
                st.caption("Среди связей нет документов с известным путём к файлу.")
            else:
                for n in sorted(docs_here, key=lambda x: x.get("name") or ""):
                    st.markdown(f"- [{n['name']}]({_file_url(n['path'])})")

            st.markdown("##### Связанные объекты — нажмите «Показать связи», чтобы перейти к узлу")
            related = [n for n in data["nodes"] if n["id"] != entity_id]
            if not related:
                st.caption("У этой сущности нет связей глубже одного узла.")
            else:
                by_label: dict[str, list[dict]] = {}
                for n in related:
                    by_label.setdefault(n.get("label") or "Другое", []).append(n)
                for label in sorted(by_label):
                    nodes_of_label = sorted(by_label[label], key=lambda x: x.get("name") or "")
                    with st.expander(f"{label} ({len(nodes_of_label)})"):
                        for n in nodes_of_label:
                            rcol1, rcol2 = st.columns([4, 1])
                            with rcol1:
                                if label == "Document" and n.get("path"):
                                    st.markdown(f"[{n['name']}]({_file_url(n['path'])})")
                                else:
                                    st.markdown(n["name"])
                            with rcol2:
                                if st.button("Показать связи", key=f"nav_{n['id']}"):
                                    st.session_state["_pending_focus_id"] = n["id"]
                                    st.rerun()

            focus_node = next((n for n in data["nodes"] if n["id"] == entity_id), None)
            if focus_node and focus_node.get("label") == "Document" and focus_node.get("path"):
                st.markdown(
                    f'<a href="{_file_url(focus_node["path"])}" target="_blank" '
                    f'style="display:inline-block;background:#0079c2;color:#fff;padding:10px 20px;'
                    f'border-radius:6px;text-decoration:none;font-weight:500;margin:10px 0;">'
                    f'Открыть / скачать документ</a>',
                    unsafe_allow_html=True,
                )
            if focus_node and focus_node.get("label") == "Material":
                try:
                    gaps_rows = requests.get(f"{API}/gaps", timeout=30).json()
                except Exception:
                    gaps_rows = []
                missing = [g for g in gaps_rows
                          if g["material"] == focus_node["name"] and g["n_experiments"] == 0]
                if missing:
                    props = ", ".join(g["property"] for g in missing)
                    st.markdown(
                        f'<div style="background:#fff7ed;border-left:4px solid #f59e0b;'
                        f'padding:10px 16px;border-radius:0 6px 6px 0;margin:10px 0;">'
                        f'<b>Пробелы для «{focus_node["name"]}»:</b> нет ни одного эксперимента '
                        f'по показателям — {props}</div>',
                        unsafe_allow_html=True,
                    )
                try:
                    experts = requests.get(f"{API}/experts/{entity_id}", timeout=30).json()
                except Exception:
                    experts = []
                if experts:
                    st.markdown(f"**Эксперты и лаборатории по «{focus_node['name']}»**")
                    st.dataframe(
                        pd.DataFrame(experts).rename(
                            columns={"person": "Эксперт", "role": "Роль", "lab": "Лаборатория"}
                        ),
                        use_container_width=True, hide_index=True,
                    )

# ---------------- Пробелы ----------------
with tab_gaps:
    st.markdown(
        "Матрица **Материал × Свойство**: количество экспериментов с измеренным эффектом. "
        "**Нули (—)** — неисследованные комбинации, кандидаты на новые НИОКР."
    )
    if st.button("Построить матрицу пробелов"):
        with st.spinner("Читаю граф..."):
            rows = requests.get(f"{API}/gaps", timeout=60).json()
        df = pd.DataFrame(rows)
        if df.empty:
            st.warning("Граф пуст — загрузите данные.")
        else:
            pivot = df.pivot(index="material", columns="property", values="n_experiments").fillna(0)
            import plotly.express as px

            fig = px.imshow(
                pivot, text_auto=True, aspect="auto",
                color_continuous_scale=[[0.0, "#eff7fa"], [0.001, "#cfe8f6"], [1.0, "#0079c2"]],
                labels=dict(color="экспериментов"),
            )
            fig.update_layout(
                height=480, margin=dict(l=10, r=10, t=30, b=10),
                font=dict(family="Onest, Arial, sans-serif", color="#162c3e"),
                paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
            )
            st.plotly_chart(fig, use_container_width=True)
            gaps = df[df.n_experiments == 0]
            if len(gaps):
                st.markdown(
                    f'<div style="background:#fff;border-left:4px solid #0079c2;'
                    f'padding:10px 16px;border-radius:0 6px 6px 0;margin:8px 0;'
                    f'box-shadow:0 1px 3px rgba(22,44,62,.06);">'
                    f'<b style="color:#162c3e">Пробелы: {len(gaps)} комбинаций</b> — '
                    f'потенциальные направления для новых НИОКР</div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(
                    gaps[["material", "property"]].rename(
                        columns={"material": "Материал", "property": "Свойство"}
                    ),
                    use_container_width=True, hide_index=True,
                )

    st.divider()
    st.markdown(
        "Матрица **Материал × Режим**: какие комбинации материал–технология не изучены "
        "или слабо освещены (по числу экспериментов)."
    )
    if st.button("Построить матрицу материал × режим"):
        rows, err = _safe_get(f"{API}/gaps/mode", timeout=60)
        if err:
            st.warning(err)
        else:
            df = pd.DataFrame(rows)
            if df.empty:
                st.warning("Граф пуст — загрузите данные.")
            else:
                pivot = df.pivot(index="material", columns="mode", values="n_experiments").fillna(0)
                import plotly.express as px

                fig = px.imshow(
                    pivot, text_auto=True, aspect="auto",
                    color_continuous_scale=[[0.0, "#eff7fa"], [0.001, "#cfe8f6"], [1.0, "#0079c2"]],
                    labels=dict(color="экспериментов"),
                )
                fig.update_layout(
                    height=480, margin=dict(l=10, r=10, t=30, b=10),
                    font=dict(family="Onest, Arial, sans-serif", color="#162c3e"),
                    paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                )
                st.plotly_chart(fig, use_container_width=True)
                gaps_mode = df[df.n_experiments == 0]
                if len(gaps_mode):
                    st.markdown(
                        f'<div style="background:#fff;border-left:4px solid #0079c2;'
                        f'padding:10px 16px;border-radius:0 6px 6px 0;margin:8px 0;'
                        f'box-shadow:0 1px 3px rgba(22,44,62,.06);">'
                        f'<b style="color:#162c3e">Пробелы: {len(gaps_mode)} комбинаций</b> — '
                        f'материал+режим без единого эксперимента</div>',
                        unsafe_allow_html=True,
                    )
                    st.dataframe(
                        gaps_mode[["material", "mode"]].rename(
                            columns={"material": "Материал", "mode": "Режим/технология"}
                        ),
                        use_container_width=True, hide_index=True,
                    )

    st.divider()
    st.markdown(
        "**Технологии по географии практики** — какие технологии описаны только в отечественных "
        "источниках, только в зарубежных, или в обеих."
    )
    if st.button("Показать покрытие по географии"):
        rows, err = _safe_get(f"{API}/mode-geography", timeout=60)
        if err:
            st.warning(err)
        else:
            df = pd.DataFrame(rows)
            if df.empty:
                st.warning("Граф пуст — загрузите данные.")
            else:
                only_one_side = df[df["coverage"].isin(["только РФ", "только зарубеж"])]
                unknown_n = int((df["coverage"] == "география не извлечена").sum())
                st.caption(
                    f"Всего технологий: {len(df)} · с географией только с одной стороны: "
                    f"{len(only_one_side)} · без данных о географии: {unknown_n}"
                )
                st.dataframe(
                    df.rename(columns={"mode": "Технология/режим", "coverage": "Покрытие"}),
                    use_container_width=True, hide_index=True,
                )

    st.divider()
    st.markdown(
        "**Противоречия в данных** — выводы с противоположным эффектом на один показатель. "
        "Тип «потенциальное» — кандидаты, требующие подтверждения экспертом."
    )
    if st.button("Найти противоречия"):
        with st.spinner("Ищу разногласия..."):
            rows = requests.get(f"{API}/contradictions", timeout=60).json()
        if not rows:
            st.info("Противоречий не найдено.")
        else:
            st.dataframe(
                pd.DataFrame(rows).rename(columns={
                    "property": "Показатель", "material": "Материал",
                    "finding_a": "Вывод А", "source_a": "Источник А",
                    "finding_b": "Вывод Б", "source_b": "Источник Б",
                }),
                use_container_width=True, hide_index=True,
            )

# ---------------- Библиотека документов ----------------
with tab_library:
    st.markdown(
        "Все файлы корпуса по папкам — открыть в браузере или скачать. "
        "Список читается напрямую из папки с данными на сервере."
    )
    if st.button("Загрузить список файлов"):
        with st.spinner("Читаю папку..."):
            lib_data, lib_err = _safe_get(f"{API}/library", timeout=60)
        if lib_err:
            st.warning(lib_err)
        else:
            st.session_state.library = lib_data
    if PUBLIC_API == API:
        st.caption(
            "Ссылки на файлы сейчас строятся по внутреннему адресу API — если открытие/скачивание "
            "не работает из браузера, задайте переменную PUBLIC_API_URL (публичный адрес сервера) "
            "при запуске UI."
        )

    lib = st.session_state.get("library")
    if not lib:
        st.info("Нажмите «Загрузить список файлов», чтобы увидеть библиотеку.")
    else:
        col1, col2 = st.columns([1, 2])
        with col1:
            cat = st.selectbox("Папка", ["Все"] + sorted(lib.keys()))
        with col2:
            search = st.text_input("Поиск по названию файла", "")

        rows = []
        for category, files in lib.items():
            if cat != "Все" and category != cat:
                continue
            for f in files:
                if search and search.lower() not in f["name"].lower():
                    continue
                rows.append({"category": category, **f})

        total_files = sum(len(v) for v in lib.values())
        st.caption(f"Всего в библиотеке: {total_files} файлов · показано: {min(len(rows), 300)} из {len(rows)}")

        for f in rows[:300]:
            url = _file_url(f["path"])
            st.markdown(
                f'<div style="background:#fff;border:1px solid #d6dfe4;border-radius:8px;'
                f'padding:8px 14px;margin-bottom:6px;display:flex;justify-content:space-between;'
                f'align-items:center;">'
                f'<span><a href="{url}" target="_blank" style="color:#0079c2;font-weight:500;'
                f'text-decoration:none;">{f["name"]}</a>'
                f'<span style="color:#6b7984;font-size:12px;"> · {f["category"]}</span></span>'
                f'<span style="color:#6b7984;font-size:12px;white-space:nowrap;">{f["size_kb"]} КБ</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
