"""Unit tests and property tests for the dashboard module."""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from modules.dashboard import (
    DashboardData,
    DashboardKPIs,
    SEVERITY_ORDER,
    VALID_CATEGORIES,
    _build_alerts,
    _compute_kpis,
    _get_recent_documents,
    _group_insights_by_category,
    _severity_score,
    get_dashboard_data,
)


class TestSeverityScore:
    def test_critical_is_highest(self):
        assert _severity_score({"severity": "Critical"}) == 3

    def test_low_is_lowest(self):
        assert _severity_score({"severity": "Low"}) == 0

    def test_unknown_defaults_to_zero(self):
        assert _severity_score({"severity": "Unknown"}) == 0

    def test_missing_severity_defaults_to_zero(self):
        assert _severity_score({}) == 0


class TestComputeKPIs:
    def test_counts_processed_statuses(self):
        docs = [
            {"status": "extracted"},
            {"status": "pending_review"},
            {"status": "approved"},
            {"status": "rejected"},
        ]
        kpis = _compute_kpis(docs, critical_count=0)
        assert kpis.total_processed == 4

    def test_counts_pending_statuses(self):
        docs = [
            {"status": "uploaded"},
            {"status": "classifying"},
            {"status": "classified"},
            {"status": "extracting"},
            {"status": "extracted"},
            {"status": "generating_insights"},
        ]
        kpis = _compute_kpis(docs, critical_count=0)
        assert kpis.pending_documents == 6

    def test_counts_pending_reviews(self):
        docs = [
            {"status": "pending_review"},
            {"status": "pending_review"},
            {"status": "approved"},
        ]
        kpis = _compute_kpis(docs, critical_count=0)
        assert kpis.pending_reviews == 2

    def test_critical_alerts_passthrough(self):
        kpis = _compute_kpis([], critical_count=7)
        assert kpis.critical_alerts == 7

    def test_empty_documents(self):
        kpis = _compute_kpis([], critical_count=0)
        assert kpis == DashboardKPIs(0, 0, 0, 0)


class TestGroupInsightsByCategory:
    def test_groups_into_valid_categories(self):
        insights = [
            {"category": "Compliance", "severity": "High"},
            {"category": "Qualidade", "severity": "Low"},
            {"category": "Financeiro", "severity": "Critical"},
            {"category": "Operacional", "severity": "Medium"},
        ]
        grouped = _group_insights_by_category(insights)
        assert len(grouped["Compliance"]) == 1
        assert len(grouped["Qualidade"]) == 1
        assert len(grouped["Financeiro"]) == 1
        assert len(grouped["Operacional"]) == 1

    def test_max_5_per_category(self):
        insights = [{"category": "Compliance", "severity": "Low"} for _ in range(10)]
        grouped = _group_insights_by_category(insights)
        assert len(grouped["Compliance"]) == 5

    def test_sorted_by_severity_descending(self):
        insights = [
            {"category": "Compliance", "severity": "Low"},
            {"category": "Compliance", "severity": "Critical"},
            {"category": "Compliance", "severity": "Medium"},
        ]
        grouped = _group_insights_by_category(insights)
        severities = [i["severity"] for i in grouped["Compliance"]]
        assert severities == ["Critical", "Medium", "Low"]

    def test_ignores_unknown_categories(self):
        insights = [{"category": "Unknown", "severity": "High"}]
        grouped = _group_insights_by_category(insights)
        assert all(len(v) == 0 for v in grouped.values())

    def test_empty_insights(self):
        grouped = _group_insights_by_category([])
        assert grouped == {
            "Compliance": [],
            "Qualidade": [],
            "Financeiro": [],
            "Operacional": [],
        }


class TestBuildAlerts:
    def test_only_high_and_critical(self):
        insights = [
            {"severity": "Critical", "title": "a"},
            {"severity": "High", "title": "b"},
            {"severity": "Medium", "title": "c"},
            {"severity": "Low", "title": "d"},
        ]
        alerts = _build_alerts(insights)
        assert len(alerts) == 2
        assert all(a["severity"] in ("Critical", "High") for a in alerts)

    def test_sorted_critical_first(self):
        insights = [
            {"severity": "High", "title": "b"},
            {"severity": "Critical", "title": "a"},
            {"severity": "High", "title": "c"},
        ]
        alerts = _build_alerts(insights)
        assert alerts[0]["severity"] == "Critical"

    def test_max_20_alerts(self):
        insights = [{"severity": "Critical", "title": f"a{i}"} for i in range(25)]
        alerts = _build_alerts(insights)
        assert len(alerts) == 20

    def test_empty_when_no_high_or_critical(self):
        insights = [
            {"severity": "Medium", "title": "a"},
            {"severity": "Low", "title": "b"},
        ]
        assert _build_alerts(insights) == []


class TestGetRecentDocuments:
    def test_sorted_by_processed_at_descending(self):
        docs = [
            {"file_name": "a.pdf", "processed_at": "2024-01-01T00:00:00"},
            {"file_name": "c.pdf", "processed_at": "2024-03-01T00:00:00"},
            {"file_name": "b.pdf", "processed_at": "2024-02-01T00:00:00"},
        ]
        recent = _get_recent_documents(docs)
        names = [d["file_name"] for d in recent]
        assert names == ["c.pdf", "b.pdf", "a.pdf"]

    def test_max_10_documents(self):
        docs = [
            {"file_name": f"doc{i}.pdf", "processed_at": f"2024-01-{i + 1:02d}T00:00:00"}
            for i in range(15)
        ]
        recent = _get_recent_documents(docs)
        assert len(recent) == 10

    def test_excludes_documents_without_processed_at(self):
        docs = [
            {"file_name": "a.pdf", "processed_at": "2024-01-01T00:00:00"},
            {"file_name": "b.pdf"},
            {"file_name": "c.pdf", "processed_at": None},
        ]
        recent = _get_recent_documents(docs)
        assert len(recent) == 1
        assert recent[0]["file_name"] == "a.pdf"


class TestGetDashboardData:
    @patch("modules.dashboard.scan_items")
    def test_returns_complete_dashboard(self, mock_scan):
        mock_scan.side_effect = [
            {
                "items": [
                    {"document_id": "1", "status": "approved", "processed_at": "2024-01-01T00:00:00"},
                    {"document_id": "2", "status": "pending_review", "processed_at": "2024-02-01T00:00:00"},
                ],
                "last_evaluated_key": None,
            },
            {
                "items": [
                    {"insight_id": "i1", "category": "Compliance", "severity": "Critical"},
                    {"insight_id": "i2", "category": "Qualidade", "severity": "High"},
                ],
                "last_evaluated_key": None,
            },
        ]

        data = get_dashboard_data()

        assert isinstance(data, DashboardData)
        assert data.kpis.total_processed == 2
        assert data.kpis.pending_reviews == 1
        assert data.kpis.critical_alerts == 1
        assert len(data.insights_by_category["Compliance"]) == 1
        assert len(data.alerts) == 2
        assert len(data.recent_documents) == 2

    @patch("modules.dashboard.scan_items")
    def test_returns_empty_dashboard_on_error(self, mock_scan):
        mock_scan.side_effect = Exception("DynamoDB unavailable")

        data = get_dashboard_data()

        assert data.kpis.total_processed == 0
        assert data.kpis.pending_documents == 0
        assert data.alerts == []
        assert data.recent_documents == []

    @patch("modules.dashboard.scan_items")
    def test_handles_pagination(self, mock_scan):
        mock_scan.side_effect = [
            {
                "items": [{"document_id": "1", "status": "approved", "processed_at": "2024-01-01T00:00:00"}],
                "last_evaluated_key": {"document_id": "1"},
            },
            {
                "items": [{"document_id": "2", "status": "uploaded"}],
                "last_evaluated_key": None,
            },
            {
                "items": [],
                "last_evaluated_key": None,
            },
        ]

        data = get_dashboard_data()

        assert data.kpis.total_processed == 1
        assert data.kpis.pending_documents == 1


# Feature: document-intelligence-copilot, Property 13: Dashboard insights grouping and alerts ordering

VALID_SEVERITIES = list(SEVERITY_ORDER.keys())

# Strategy: random insight dicts with valid categories and severities
insight_strategy = st.fixed_dictionaries(
    {
        "category": st.sampled_from(["Compliance", "Qualidade", "Financeiro", "Operacional"]),
        "severity": st.sampled_from(["Low", "Medium", "High", "Critical"]),
        "title": st.text(min_size=1, max_size=50),
    }
)

insights_list_strategy = st.lists(insight_strategy, min_size=0, max_size=30)


class TestProperty13DashboardInsightsGroupingAndAlertsOrdering:
    """Property 13: Dashboard insights grouping and alerts ordering.

    **Validates: Requirements 6.2, 6.3**
    """

    @given(insights=insights_list_strategy)
    @settings(max_examples=20)
    def test_p13a_grouped_output_has_exactly_4_categories_with_max_5_each(
        self, insights: list[dict]
    ):
        """P13a: Grouped output has exactly 4 valid category keys, each ≤ 5 items,
        sorted by severity descending.

        **Validates: Requirements 6.2**
        """
        grouped = _group_insights_by_category(insights)

        assert set(grouped.keys()) == set(VALID_CATEGORIES)
        assert len(grouped) == 4

        for cat in VALID_CATEGORIES:
            items = grouped[cat]
            assert len(items) <= 5
            scores = [SEVERITY_ORDER.get(i.get("severity", "Low"), 0) for i in items]
            assert scores == sorted(scores, reverse=True)

    @given(insights=insights_list_strategy)
    @settings(max_examples=20)
    def test_p13b_alerts_max_20_only_high_critical_sorted_by_severity(
        self, insights: list[dict]
    ):
        """P13b: Alerts list has ≤ 20 items, only High/Critical, sorted Critical > High.

        **Validates: Requirements 6.3**
        """
        alerts = _build_alerts(insights)

        assert len(alerts) <= 20
        assert all(a.get("severity") in ("Critical", "High") for a in alerts)

        scores = [SEVERITY_ORDER.get(a.get("severity", "Low"), 0) for a in alerts]
        assert scores == sorted(scores, reverse=True)
