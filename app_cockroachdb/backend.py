"""CockroachDB backend adapter for abstract app composition."""

from __future__ import annotations

from typing import Any

from app_abstract.backends.common import SqlBackendAdapter
from app_abstract.shared_db import fetch_all, fetch_one
from app_cockroachdb.db import get_conn
from app_cockroachdb.trade_service import TradeService


class CockroachBackend(SqlBackendAdapter):
    """Backend adapter for CockroachDB deployment."""

    INTERNAL_SHARDING_NOTE = (
        "CockroachDB handles sharding internally; no explicit shard metadata exposed in single-node mode"
    )

    def __init__(self) -> None:
        super().__init__(
            backend_id="cockroachdb",
            app_title="sliderule Prototype (CockroachDB)",
            startup_label="CockroachDB",
            fetch_all_fn=fetch_all,
            fetch_one_fn=fetch_one,
            get_conn_fn=get_conn,
            trade_service=TradeService(),
        )

    def get_cluster_status(self) -> dict[str, Any]:
        counts = self.fetch_entity_counts()
        return self.build_single_node_cluster_status(backend=self.backend_id, counts=counts)

    def get_shard_status(self) -> dict[str, Any]:
        return self.build_internal_sharding_status(backend=self.backend_id, note=self.INTERNAL_SHARDING_NOTE)
