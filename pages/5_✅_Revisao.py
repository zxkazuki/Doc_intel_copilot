"""Painel de Revisão — visualização lado a lado, validação e ações sobre o documento."""

import time

import streamlit as st

from modules.review import approve_document, reject_document, correct_field, FieldCorrection
from modules.history import get_document_history, get_document_detail, HistoryFilters
from modules.laudo import generate_laudo
from modules.reporting import build_review_pdf, build_laudo_pdf
from modules.chat import chat_with_agent
from infrastructure.s3_client import generate_presigned_url

STATUS_LABELS = {
    "pending_review": "🟡 Aguardando Revisão",
    "approved": "🟢 Aprovado",
    "rejected": "🔴 Rejeitado",
    "extracted": "🔵 Extraído",
    "uploaded": "🔵 Enviado",
}

STATUS_FILTERS = {
    "Aguardando Revisão": "pending_review",
    "Aprovados": "approved",
    "Rejeitados": "rejected",
    "Todos": None,
}

ACTION_LABELS = {"approve": "✅ Aprovação", "reject": "❌ Rejeição", "correction": "✏️ Correção"}


def _to_float(value) -> float:
    """Safely convert a confidence value (str/Decimal/float/None) to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _status_label(status: str) -> str:
    """Return a human-friendly status badge."""
    return STATUS_LABELS.get(status, status)


st.set_page_config(page_title="Revisão", page_icon="✅", layout="wide")
st.header("✅ Painel de Revisão")
st.markdown("Revise os dados extraídos lado a lado com o documento original.")

# --- Status filter + document selector ---
col_filter, col_doc_select = st.columns([1, 3])

with col_filter:
    filter_label = st.selectbox(
        "Filtrar por status",
        options=list(STATUS_FILTERS.keys()),
        index=0,
    )
status_filter = STATUS_FILTERS[filter_label]

docs = get_document_history(HistoryFilters(status=status_filter, page_size=100)).items

if not docs:
    st.info("Nenhum documento encontrado para o filtro selecionado.")
    st.stop()

with col_doc_select:
    doc_options = {
        doc["document_id"]: f"{doc.get('file_name', doc['document_id'])} — {_status_label(doc.get('status', ''))}"
        for doc in docs
    }
    selected_id = st.selectbox(
        "Selecione um documento",
        options=list(doc_options.keys()),
        format_func=lambda doc_id: doc_options[doc_id],
    )

# Load document detail
detail = get_document_detail(selected_id)
if not detail:
    st.error("Não foi possível carregar os detalhes do documento.")
    st.stop()

document = detail["document"]
extraction = detail.get("extraction")
fields = (extraction or {}).get("fields", [])
current_status = document.get("status", "")

st.markdown(f"**Status atual:** {_status_label(current_status)}")

if not fields:
    st.warning("Nenhum campo extraído disponível para este documento.")
    st.stop()

# --- Side-by-side layout ---
col_doc, col_fields = st.columns(2)

# Column 1: Document viewer
with col_doc:
    st.subheader("📄 Documento Original")
    s3_key = document.get("s3_key", "")
    presigned_url = generate_presigned_url(s3_key) if s3_key else ""

    if not presigned_url:
        st.warning("Não foi possível gerar URL de acesso ao documento.")
    elif document.get("file_format", "").lower() == "pdf":
        st.markdown(
            f'<iframe src="{presigned_url}" width="100%" height="600" '
            f'type="application/pdf"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.image(presigned_url, use_container_width=True)

# Column 2: Editable fields
with col_fields:
    st.subheader("📋 Campos Extraídos")

    state_key = f"review_fields_{selected_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = {f["name"]: f.get("value") or "" for f in fields}

    for field_data in fields:
        name = field_data["name"]
        confidence = _to_float(field_data.get("confidence", 0.0))
        current_value = st.text_input(
            f"{name} (confiança: {confidence:.0%})",
            value=st.session_state[state_key].get(name, ""),
            key=f"field_{selected_id}_{name}",
        )
        st.session_state[state_key][name] = current_value

# --- Approve / Reject buttons (always available) ---
st.divider()
st.subheader("⚖️ Decisão de Revisão")
if current_status == "approved":
    st.success("Este documento já foi APROVADO. Você pode reprocessar a decisão se necessário.")
elif current_status == "rejected":
    st.error("Este documento já foi REJEITADO. Você pode reprocessar a decisão se necessário.")

btn_approve, btn_reject, _ = st.columns([1, 1, 3])
approve_clicked = btn_approve.button("✅ Aprovar", type="primary", use_container_width=True)
reject_clicked = btn_reject.button("❌ Rejeitar", type="secondary", use_container_width=True)

if approve_clicked:
    corrections_failed = False
    for field_data in fields:
        name = field_data["name"]
        original = field_data.get("value") or ""
        edited = st.session_state[state_key].get(name, original)
        if edited == original:
            continue
        ok = correct_field(
            selected_id,
            reviewer_id="streamlit_user",
            correction=FieldCorrection(
                field_name=name,
                original_value=original,
                corrected_value=edited,
            ),
        )
        if not ok:
            corrections_failed = True
            break

    if corrections_failed:
        st.error("Falha ao salvar correções. Seus dados editados foram preservados.")
    elif not approve_document(selected_id, reviewer_id="streamlit_user"):
        st.error("Falha ao aprovar documento. Seus dados editados foram preservados.")
    else:
        st.success("Documento aprovado com sucesso!")
        st.rerun()

if reject_clicked:
    if reject_document(selected_id, reviewer_id="streamlit_user"):
        st.success("Documento rejeitado.")
        st.rerun()
    else:
        st.error("Falha ao rejeitar documento. Tente novamente.")

# --- Review history (audit trail) ---
reviews = detail.get("reviews", [])
if reviews:
    with st.expander(f"📝 Histórico de Revisões ({len(reviews)})", expanded=False):
        for review in sorted(reviews, key=lambda r: r.get("timestamp", ""), reverse=True):
            action = review.get("action", "—")
            reviewer = review.get("reviewer_id", "Desconhecido")
            timestamp = review.get("timestamp", "—")
            st.markdown(f"**{ACTION_LABELS.get(action, action)}** — {reviewer} em `{timestamp}`")
            if action == "correction" and review.get("field_name"):
                original = review.get("original_value") or "—"
                new = review.get("new_value") or "—"
                st.caption(f"Campo **{review['field_name']}**: `{original}` → `{new}`")

# --- Export & Actions (always available) ---
st.divider()
st.subheader("📤 Exportações e Ações")

laudo_key = f"laudo_{selected_id}"
file_stem = document.get("file_name", "documento").rsplit(".", 1)[0]

col1, col2, col3, col4 = st.columns(4)

# 1. Export PDF (review data)
with col1:
    pdf_bytes = build_review_pdf(detail)
    st.download_button(
        "📄 Exportar PDF",
        data=pdf_bytes,
        file_name=f"{file_stem}_revisao.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

# 2. Generate + export AI laudo
with col2:
    if st.button("🧾 Exportar Revisão (Laudo IA)", use_container_width=True):
        with st.spinner("Gerando laudo com IA..."):
            result = generate_laudo(selected_id)
        if result.success:
            st.session_state[laudo_key] = result.content
        else:
            st.error(result.error_message or "Falha ao gerar laudo.")

# 3. Export to system (fake)
with col3:
    if st.button("🗄️ Exportar para Sistema", use_container_width=True):
        progress = st.progress(0, text="Conectando ao sistema...")
        steps = [
            (20, "Autenticando no ERP..."),
            (45, "Validando dados extraídos..."),
            (70, "Enviando registros..."),
            (90, "Confirmando integração..."),
            (100, "Concluído!"),
        ]
        for pct, label in steps:
            time.sleep(0.6)
            progress.progress(pct, text=label)
        st.success("✅ Seus dados foram inputados no sistema XPTO ERP com sucesso!")

# 4. Chat toggle
with col4:
    chat_open_key = f"chat_open_{selected_id}"
    if st.button("💬 Conversar com Agente IA", use_container_width=True):
        st.session_state[chat_open_key] = not st.session_state.get(chat_open_key, False)

# Show generated laudo (if any) with download
if st.session_state.get(laudo_key):
    st.divider()
    st.subheader("🧾 Laudo de Revisão (IA)")
    st.markdown(st.session_state[laudo_key])
    laudo_pdf = build_laudo_pdf(detail, st.session_state[laudo_key])
    st.download_button(
        "⬇️ Baixar Laudo em PDF",
        data=laudo_pdf,
        file_name=f"{file_stem}_laudo.pdf",
        mime="application/pdf",
    )

# --- AI Chat interface ---
if st.session_state.get(f"chat_open_{selected_id}", False):
    st.divider()
    st.subheader("💬 Agente de IA — Converse sobre o documento")

    history_key = f"chat_history_{selected_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    for msg in st.session_state[history_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Pergunte sobre o documento, insights ou laudo...")
    if user_msg:
        st.session_state[history_key].append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                answer = chat_with_agent(
                    document_id=selected_id,
                    history=st.session_state[history_key],
                    laudo_text=st.session_state.get(laudo_key, ""),
                )
            st.markdown(answer)

        st.session_state[history_key].append({"role": "assistant", "content": answer})
