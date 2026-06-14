"""Página Histórico — consulta de documentos processados com filtros e paginação."""

import streamlit as st
import pandas as pd

from modules.history import get_document_history, HistoryFilters

CATEGORY_OPTIONS: list[str] = [
    "Todas",
    "Contrato",
    "Laudo Médico",
    "Extrato Bancário",
    "Ficha Cadastral",
    "Nota Fiscal",
    "Documento Genérico",
]

STATUS_OPTIONS: list[str] = [
    "Todos",
    "uploaded",
    "classified",
    "extracted",
    "pending_review",
    "approved",
    "rejected",
]

PAGE_SIZE = 20


def _init_session_state() -> None:
    """Inicializa variáveis de estado da página."""
    if "history_page" not in st.session_state:
        st.session_state["history_page"] = 1


def _render_sidebar() -> HistoryFilters:
    """Renderiza filtros na sidebar e retorna HistoryFilters construído."""
    with st.sidebar:
        st.header("🔎 Filtros")

        category = st.selectbox("Categoria", CATEGORY_OPTIONS, index=0)
        status = st.selectbox("Status", STATUS_OPTIONS, index=0)
        date_from = st.date_input("Data início", value=None)
        date_to = st.date_input("Data fim", value=None)
        search_text = st.text_input(
            "Pesquisar",
            value="",
            help="Mínimo 3 caracteres",
        )

    return HistoryFilters(
        category=None if category == "Todas" else category,
        status=None if status == "Todos" else status,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None,
        search_text=search_text if len(search_text) >= 3 else None,
        page=st.session_state["history_page"],
        page_size=PAGE_SIZE,
    )


def _render_table(items: list[dict]) -> None:
    """Renderiza tabela de documentos com seleção de linha."""
    rows = [
        {
            "Arquivo": doc.get("file_name", "—"),
            "Categoria": doc.get("category", "—"),
            "Status": doc.get("status", "—"),
            "Processado em": doc.get("processed_at", "—"),
            "Severidade": doc.get("max_severity", "—"),
        }
        for doc in items
    ]

    event = st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    if not (event and event.selection and event.selection.rows):
        return

    selected_doc = items[event.selection.rows[0]]
    document_id = selected_doc.get("document_id", "")
    if document_id:
        st.query_params["document_id"] = document_id
        st.switch_page("pages/4_🔍_Detalhes.py")


def _render_pagination(total: int, has_next: bool) -> None:
    """Renderiza controles de navegação prev/next."""
    current_page = st.session_state["history_page"]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    col_prev, col_info, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button("⬅️ Anterior", disabled=(current_page <= 1)):
            st.session_state["history_page"] = current_page - 1
            st.rerun()

    with col_info:
        st.markdown(
            f"<div style='text-align: center;'>Página {current_page} de {total_pages}</div>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button("Próxima ➡️", disabled=(not has_next)):
            st.session_state["history_page"] = current_page + 1
            st.rerun()


def main() -> None:
    """Entry point da página Histórico."""
    st.set_page_config(page_title="Histórico", page_icon="📋", layout="wide")
    st.title("📋 Histórico de Documentos")

    _init_session_state()
    filters = _render_sidebar()
    result = get_document_history(filters)

    if not result.items:
        st.info("Nenhum documento encontrado. Tente remover os filtros aplicados.")
        return

    _render_table(result.items)
    st.divider()
    _render_pagination(result.total, result.has_next)


main()
