"""Upload de Documentos — Pipeline de processamento completo."""

import streamlit as st

from modules.upload import upload_document, validate_file
from modules.classifier import classify_document
from modules.extractor import extract_fields
from modules.insights import generate_insights

st.set_page_config(page_title="Upload", page_icon="📤", layout="wide")
st.header("📤 Upload de Documentos")
st.markdown("Envie um documento para processamento automático pelo pipeline de inteligência.")


def _run_pipeline(file_bytes: bytes, file_name: str, file_size: int) -> None:
    """Execute the full processing pipeline with visual status updates."""
    with st.status("🔄 Processando documento...", expanded=True) as status:
        # Step 1: Upload
        st.write("📤 Enviando documento...")
        upload_result = upload_document(file_bytes, file_name, file_size)
        if not upload_result.success:
            status.update(label="❌ Falha no upload", state="error")
            st.error(upload_result.error_message)
            return
        st.write("✅ Upload concluído")

        doc_id = upload_result.document_id

        # Step 2: Classification
        st.write("🏷️ Classificando documento...")
        classification_result = classify_document(doc_id)
        if not classification_result.success:
            status.update(label="❌ Falha na classificação", state="error")
            st.error(classification_result.error_message)
            return
        st.write(f"✅ Classificado como: **{classification_result.category}** "
                 f"(confiança: {classification_result.confidence:.0%})")

        # Step 3: Extraction
        st.write("📋 Extraindo campos...")
        extraction_result = extract_fields(doc_id)
        if not extraction_result.success:
            status.update(label="❌ Falha na extração", state="error")
            st.error(extraction_result.error_message)
            return
        st.write(f"✅ {len(extraction_result.fields)} campos extraídos")

        # Step 4: Insights
        st.write("💡 Gerando insights...")
        insights_result = generate_insights(doc_id)
        if not insights_result.success:
            status.update(label="❌ Falha na geração de insights", state="error")
            st.error(insights_result.error_message)
            return
        st.write(f"✅ {len(insights_result.insights)} insights gerados")

        status.update(label="✅ Documento processado com sucesso!", state="complete")

    # Summary
    st.success(
        f"**Documento processado!** "
        f"Categoria: {classification_result.category} · "
        f"Campos: {len(extraction_result.fields)} · "
        f"Insights: {len(insights_result.insights)}"
    )


# File uploader
uploaded_file = st.file_uploader(
    "Selecione um arquivo",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=False,
    help="Formatos aceitos: PDF, PNG, JPG, JPEG. Tamanho máximo: 20 MB.",
)

if uploaded_file is not None:
    # Validate before processing
    validation = validate_file(uploaded_file.name, uploaded_file.size)

    if not validation.valid:
        st.error(validation.error_message)
    else:
        file_bytes = uploaded_file.getvalue()
        _run_pipeline(file_bytes, uploaded_file.name, uploaded_file.size)
