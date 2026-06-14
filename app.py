"""Document Intelligence Copilot — Streamlit entry point."""

import streamlit as st

st.set_page_config(
    page_title="Document Intelligence Copilot",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Document Intelligence Copilot")
st.markdown(
    "Plataforma de processamento inteligente de documentos. "
    "Transforme PDFs e imagens em dados estruturados, insights acionáveis e alertas operacionais."
)

st.divider()

st.markdown(
    """
    ### Como funciona

    1. **📤 Upload** — Envie documentos (PDF, PNG, JPG, JPEG) de até 20 MB
    2. **🏷️ Classificação** — IA identifica automaticamente a categoria do documento
    3. **📋 Extração** — Campos estruturados são extraídos conforme a categoria
    4. **💡 Insights** — Inconsistências e alertas são detectados automaticamente
    5. **✅ Revisão** — Valide e corrija os dados extraídos

    Use o menu lateral para navegar entre as páginas.
    """
)
