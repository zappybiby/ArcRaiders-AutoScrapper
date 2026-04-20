"""Tests for ArcTracker API client and orchestrator."""

import pytest
from unittest.mock import patch
from autoscrapper.api.client import ArcTrackerClient, APIOrchestrator
from autoscrapper.api.models import StashData, StashItem


@pytest.fixture
def mock_actions():
    return {"matriarch reactor": ["KEEP"], "fabric": ["SELL"]}


@pytest.fixture
def api_client():
    return ArcTrackerClient(app_key="test_app", user_key="test_user")


class TestArcTrackerClient:
    def test_headers_include_keys(self, api_client):
        headers = api_client._get_headers(require_auth=True)
        assert headers["X-App-Key"] == "test_app"
        assert headers["Authorization"] == "Bearer test_user"

    def test_rate_limit_tracking(self, api_client):
        headers = {
            "X-RateLimit-Limit": "500",
            "X-RateLimit-Remaining": "499",
            "X-RateLimit-Reset": "10",  # relative
        }
        api_client._update_rate_limit(headers)
        assert api_client.rate_limit.remaining == 499
        assert api_client.rate_limit.reset_timestamp > 0


class TestAPIOrchestrator:
    def test_get_item_decisions_maps_correctly(self, api_client, mock_actions):
        orchestrator = APIOrchestrator(api_client, mock_actions)

        mock_stash = StashData(
            items=[
                StashItem(
                    item_id="1",
                    name="Matriarch Reactor",
                    quantity=1,
                    slot=0,
                    item_type="Refined",
                    rarity="Common",
                    value=100,
                ),
                StashItem(
                    item_id="2", name="Fabric", quantity=5, slot=1, item_type="Material", rarity="Common", value=10
                ),
                StashItem(
                    item_id="3", name="Unknown Item", quantity=1, slot=2, item_type="Other", rarity="Common", value=0
                ),
            ]
        )

        with patch.object(api_client, "get_all_stash_items", return_value=mock_stash):
            decisions = orchestrator.get_item_decisions(prefer_api=True)

            assert decisions["Matriarch Reactor"] == "KEEP"
            assert decisions["Fabric"] == "SELL"
            assert "Unknown Item" not in decisions

    def test_get_item_decisions_handles_api_error(self, api_client, mock_actions):
        orchestrator = APIOrchestrator(api_client, mock_actions)

        mock_stash = StashData(api_error="Connection failed")

        with patch.object(api_client, "get_all_stash_items", return_value=mock_stash):
            decisions = orchestrator.get_item_decisions(prefer_api=True)
            assert decisions == {}
