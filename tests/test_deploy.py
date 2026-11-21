from __future__ import annotations

from pathlib import Path

CHART = Path(__file__).resolve().parents[1] / "deploy" / "helm" / "loan-draw"


def test_the_chart_keeps_the_api_and_mcp_inside_the_cluster_by_default():
    """CI has no helm, so the templates are checked as text."""
    assert "type: NodePort" not in (CHART / "templates" / "api.yaml").read_text()
    assert "serviceType: ClusterIP" in (CHART / "values.yaml").read_text()
    policy = (CHART / "templates" / "mcp.yaml").read_text().split("kind: NetworkPolicy", 1)
    assert len(policy) == 2, "nothing limits which pods can reach the MCP server"
    assert "app: {{ .Release.Name }}-api" in policy[1] and "port: 8765" in policy[1]
