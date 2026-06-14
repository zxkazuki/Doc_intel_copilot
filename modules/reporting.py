"""Geração de relatórios PDF via reportlab."""

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_PLACEHOLDER = "—"

# Cores do tema
_HEADER_BG = colors.HexColor("#1f4e79")
_HEADER_FG = colors.white
_GRID = colors.HexColor("#b0b8c1")
_ROW_ALT = colors.HexColor("#f2f5f9")

# Mapeamento de severidade para cor (destaque visual)
_SEVERITY_COLORS = {
    "low": colors.HexColor("#2e7d32"),
    "medium": colors.HexColor("#f9a825"),
    "high": colors.HexColor("#ef6c00"),
    "critical": colors.HexColor("#c62828"),
}


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_text(value) -> str:
    """Convert a value to a display string, falling back to a placeholder."""
    if value is None:
        return _PLACEHOLDER
    text = str(value).strip()
    return text if text else _PLACEHOLDER


def _escape(text: str) -> str:
    """Escape XML-sensitive characters for reportlab Paragraph markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_confidence(value) -> str:
    """Format a confidence value (stored as string) as a percentage."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _PLACEHOLDER
    ratio = _to_float(value)
    # Aceita tanto 0–1 quanto 0–100.
    pct = ratio * 100 if ratio <= 1 else ratio
    return f"{pct:.1f}%"


def _now_label() -> str:
    """Return a readable UTC timestamp for the report header."""
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _build_styles() -> dict[str, ParagraphStyle]:
    """Build a reusable set of paragraph styles."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle",
            parent=base["Title"],
            fontSize=20,
            spaceAfter=6,
            textColor=_HEADER_BG,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#5a6470"),
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontSize=13,
            textColor=_HEADER_BG,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
        ),
        "cell_header": ParagraphStyle(
            "CellHeader",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=_HEADER_FG,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            leftIndent=16,
            bulletIndent=4,
            spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "LaudoH1",
            parent=base["Heading1"],
            fontSize=16,
            textColor=_HEADER_BG,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "LaudoH2",
            parent=base["Heading2"],
            fontSize=13,
            textColor=_HEADER_BG,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "LaudoH3",
            parent=base["Heading3"],
            fontSize=11,
            textColor=colors.HexColor("#33475b"),
            spaceBefore=8,
            spaceAfter=4,
        ),
    }


def _new_doc(buffer: io.BytesIO, title: str) -> SimpleDocTemplate:
    """Create a SimpleDocTemplate with A4 page size and sensible margins."""
    return SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )


def _metadata_block(document: dict, styles: dict[str, ParagraphStyle]) -> list:
    """Build header metadata flowables from the document dict."""
    lines = [
        f"<b>Arquivo:</b> {_escape(_safe_text(document.get('file_name')))}",
        f"<b>Categoria:</b> {_escape(_safe_text(document.get('category')))}",
        f"<b>Status:</b> {_escape(_safe_text(document.get('status')))}",
        f"<b>Gerado em:</b> {_now_label()}",
    ]
    return [Paragraph("<br/>".join(lines), styles["meta"])]


def _table_style(row_count: int) -> TableStyle:
    """Return a clean table style: shaded header, grid, alternating rows."""
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    commands.extend(
        ("BACKGROUND", (0, row), (-1, row), _ROW_ALT)
        for row in range(1, row_count)
        if row % 2 == 0
    )
    return TableStyle(commands)


def _fields_table(fields: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    """Build the extracted-fields table (Campo | Valor | Confiança)."""
    header = [
        Paragraph("Campo", styles["cell_header"]),
        Paragraph("Valor", styles["cell_header"]),
        Paragraph("Confiança", styles["cell_header"]),
    ]
    rows = [header]
    rows.extend(
        [
            Paragraph(_escape(_safe_text(field.get("name"))), styles["cell"]),
            Paragraph(_escape(_safe_text(field.get("value"))), styles["cell"]),
            Paragraph(
                _escape(_format_confidence(field.get("confidence"))), styles["cell"]
            ),
        ]
        for field in fields
    )

    table = Table(rows, colWidths=[5 * cm, 8.5 * cm, 3 * cm], repeatRows=1)
    table.setStyle(_table_style(len(rows)))
    return table


def _insights_table(insights: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    """Build the insights table (Título | Severidade | Categoria | Descrição)."""
    header = [
        Paragraph("Título", styles["cell_header"]),
        Paragraph("Severidade", styles["cell_header"]),
        Paragraph("Categoria", styles["cell_header"]),
        Paragraph("Descrição", styles["cell_header"]),
    ]
    rows = [header]
    severity_colors: dict[int, colors.Color] = {}
    for idx, insight in enumerate(insights, start=1):
        severity_raw = _safe_text(insight.get("severity"))
        if sev_color := _SEVERITY_COLORS.get(severity_raw.lower()):
            severity_colors[idx] = sev_color
        rows.append(
            [
                Paragraph(_escape(_safe_text(insight.get("title"))), styles["cell"]),
                Paragraph(_escape(severity_raw), styles["cell"]),
                Paragraph(_escape(_safe_text(insight.get("category"))), styles["cell"]),
                Paragraph(
                    _escape(_safe_text(insight.get("description"))), styles["cell"]
                ),
            ]
        )

    table = Table(rows, colWidths=[4 * cm, 2.5 * cm, 3 * cm, 7 * cm], repeatRows=1)
    style = _table_style(len(rows))
    for row_idx, color in severity_colors.items():
        style.add("TEXTCOLOR", (1, row_idx), (1, row_idx), color)
        style.add("FONTNAME", (1, row_idx), (1, row_idx), "Helvetica-Bold")
    table.setStyle(style)
    return table


def build_review_pdf(detail: dict) -> bytes:
    """Gera um PDF com os dados de revisão do documento (campos + insights).

    Returns the PDF as bytes.
    """
    detail = detail or {}
    document = detail.get("document") or {}
    fields = (detail.get("extraction") or {}).get("fields") or []
    insights = detail.get("insights") or []

    styles = _build_styles()
    buffer = io.BytesIO()
    doc = _new_doc(buffer, "Relatório de Revisão de Documento")

    story: list = [
        Paragraph("Relatório de Revisão de Documento", styles["title"]),
        Paragraph(
            "Document Intelligence Copilot — dados extraídos e insights",
            styles["subtitle"],
        ),
        Paragraph("Informações do Documento", styles["section"]),
        *_metadata_block(document, styles),
        Paragraph("Campos Extraídos", styles["section"]),
        _fields_table(fields, styles)
        if fields
        else Paragraph("Nenhum campo extraído disponível.", styles["body"]),
        Paragraph("Insights", styles["section"]),
        _insights_table(insights, styles)
        if insights
        else Paragraph("Nenhum insight gerado.", styles["body"]),
    ]

    doc.build(story)
    return buffer.getvalue()


def _strip_inline_markdown(text: str) -> str:
    """Convert simple inline markdown bold (**text**) into reportlab <b> markup.

    The text is escaped first, then bold markers are restored as tags so that
    malformed markdown never breaks rendering.
    """
    escaped = _escape(text)
    parts = escaped.split("**")
    if len(parts) < 3:
        # Sem par completo de marcadores: remove resíduos e retorna texto puro.
        return escaped.replace("**", "")
    # Índices ímpares ficam entre marcadores → negrito.
    return "".join(
        f"<b>{part}</b>" if idx % 2 else part for idx, part in enumerate(parts)
    )


def _laudo_line_to_flowable(line: str, styles: dict[str, ParagraphStyle]):
    """Convert a single laudo text line into a flowable (Spacer for blanks)."""
    stripped = line.strip()
    if not stripped:
        return Spacer(1, 6)

    if stripped.startswith("#"):
        level = len(stripped) - len(stripped.lstrip("#"))
        content = stripped[level:].strip()
        style_key = {1: "h1", 2: "h2"}.get(level, "h3")
        return Paragraph(_strip_inline_markdown(content), styles[style_key])

    if stripped.startswith(("- ", "* ")):
        content = stripped[2:].strip()
        return Paragraph(
            _strip_inline_markdown(content), styles["bullet"], bulletText="•"
        )

    return Paragraph(_strip_inline_markdown(stripped), styles["body"])


def build_laudo_pdf(detail: dict, laudo_text: str) -> bytes:
    """Gera um PDF com o laudo de revisão gerado por IA.

    Args:
        detail: document detail dict (for header metadata).
        laudo_text: the AI-generated laudo (markdown-ish text).
    Returns the PDF as bytes.
    """
    detail = detail or {}
    document = detail.get("document") or {}
    laudo_text = laudo_text or ""

    styles = _build_styles()
    buffer = io.BytesIO()
    doc = _new_doc(buffer, "Laudo de Revisão")

    story: list = [
        Paragraph("Laudo de Revisão", styles["title"]),
        Paragraph(
            "Document Intelligence Copilot — laudo gerado por IA",
            styles["subtitle"],
        ),
        *_metadata_block(document, styles),
        Spacer(1, 12),
    ]

    if laudo_text.strip():
        story.extend(
            _laudo_line_to_flowable(line, styles)
            for line in laudo_text.splitlines()
        )
    else:
        story.append(
            Paragraph("Nenhum laudo disponível para este documento.", styles["body"])
        )

    doc.build(story)
    return buffer.getvalue()
