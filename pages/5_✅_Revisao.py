"""Painel de Revisão — visualização lado a lado e validação de dados extraídos."""

import streamlit as st

from modules.review import approve_document, reject_document, correct_field, FieldCorrection
from modules.history import get_document_history, get_document_detail, HistoryFilters
from infrastructure.s3_client import generate_presigned_url

st.set_page_config(page_title="Revisão", page_icon="✅", layout="wide")
st.header("✅ Painel de Revisão")
st.markdown("Revise os dados extraídos lado a lado com o documento original.")

# Load pending documents
pending_docs = get_document_history(HistoryFilters(status="pending_review")).items

if not pending_docs:
    st.info("Nenhum documento aguardando revisão.")
    st.stop()

# Document selector
doc_options = {doc["document_id"]: doc.get("file_name", doc["document_id"]) for doc in pending_docs}
selected_id = st.selectbox(
    "Selecione um documento para revisão",
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
        confidence = field_data.get("confidence", 0.0)
        current_value = st.text_input(
            f"{name} (confiança: {confidence:.0%})",
            value=st.session_state[state_key].get(name, ""),
            key=f"field_{selected_id}_{name}",
        )
        st.session_state[state_key][name] = current_value

# --- Action buttons ---
st.divider()
btn_approve, btn_reject, _ = st.columns([1, 1, 3])

approve_clicked = btn_approve.button("✅ Aprovar", type="primary", use_container_width=True)
reject_clicked = btn_reject.button("❌ Rejeitar", type="secondary", use_container_width=True)

if approve_clicked:
    # Record corrections for changed fields
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
