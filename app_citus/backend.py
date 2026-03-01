"""Citus backend adapter for abstract app composition."""

from __future__ import annotations

from typing import Any

from app_abstract.backends.common import SqlBackendAdapter
from app_abstract.shared_db import fetch_all, fetch_one
from app_citus.db import get_conn
from app_citus.trade_service import TradeService


class CitusBackend(SqlBackendAdapter):
    """Backend adapter for Citus deployment."""

    NODES_SQL = """
        SELECT nodename,
               nodeport,
               noderole,
               nodecluster,
               isactive
        FROM pg_dist_node
        ORDER BY noderole, nodename
    """
    DB_STATS_SQL = """
        SELECT numbackends,
               xact_commit,
               xact_rollback,
               blks_read,
               blks_hit,
               tup_returned,
               tup_fetched,
               tup_inserted,
               tup_updated,
               tup_deleted
        FROM pg_stat_database
        WHERE datname = current_database()
    """
    SHARDS_SQL = """
        SELECT shardid,
               shardminvalue,
               shardmaxvalue
        FROM pg_dist_shard
        WHERE logicalrelid = 'trade_events'::regclass
        ORDER BY shardid
    """
    PLACEMENTS_SQL = """
        SELECT p.shardid,
               n.nodename,
               n.nodeport,
               p.shardstate
        FROM pg_dist_placement p
        JOIN pg_dist_shard s ON s.shardid = p.shardid
        JOIN pg_dist_node n ON n.groupid = p.groupid
        WHERE s.logicalrelid = 'trade_events'::regclass
        ORDER BY p.shardid, n.nodename
    """
    REPLICA_COUNTS_SQL = """
        SELECT p.shardid,
               count(*) AS replica_count
        FROM pg_dist_placement p
        JOIN pg_dist_shard s ON s.shardid = p.shardid
        WHERE s.logicalrelid = 'trade_events'::regclass
        GROUP BY p.shardid
        ORDER BY p.shardid
    """

    def __init__(self) -> None:
        super().__init__(
            backend_id="citus",
            app_title="sliderule Prototype",
            startup_label="Citus",
            fetch_all_fn=fetch_all,
            fetch_one_fn=fetch_one,
            get_conn_fn=get_conn,
            trade_service=TradeService(),
        )

    def get_cluster_status(self) -> dict[str, Any]:
        with self.get_conn() as conn:
            shard_count = self.fetch_one(conn, "SHOW citus.shard_count")[0]
            repl_factor = self.fetch_one(conn, "SHOW citus.shard_replication_factor")[0]
            nodes = self.fetch_all(conn, self.NODES_SQL)
            db_stats = self.fetch_one(conn, self.DB_STATS_SQL)
            counts = self.fetch_entity_counts(conn=conn)

        return {
            "shards": {
                "count": int(shard_count),
                "replication_factor": int(repl_factor),
            },
            "nodes": self._serialize_nodes(nodes),
            "counts": counts,
            "db_stats": self._serialize_db_stats(db_stats),
        }

    def get_shard_status(self) -> dict[str, Any]:
        with self.get_conn() as conn:
            shards = self.fetch_all(conn, self.SHARDS_SQL)
            placements = self.fetch_all(conn, self.PLACEMENTS_SQL)
            replica_counts = self.fetch_all(conn, self.REPLICA_COUNTS_SQL)

        return {
            "shards": self._serialize_shards(shards),
            "placements": self._serialize_placements(placements),
            "replicas": self._serialize_replica_counts(replica_counts),
        }

    @staticmethod
    def _serialize_nodes(rows: list[tuple]) -> list[dict[str, Any]]:
        return [
            {
                "name": row[0],
                "port": row[1],
                "role": row[2],
                "cluster": row[3],
                "active": row[4],
            }
            for row in rows
        ]

    @staticmethod
    def _serialize_db_stats(row: tuple) -> dict[str, int]:
        return {
            "connections": int(row[0]),
            "xact_commit": int(row[1]),
            "xact_rollback": int(row[2]),
            "blks_read": int(row[3]),
            "blks_hit": int(row[4]),
            "tup_returned": int(row[5]),
            "tup_fetched": int(row[6]),
            "tup_inserted": int(row[7]),
            "tup_updated": int(row[8]),
            "tup_deleted": int(row[9]),
        }

    @staticmethod
    def _serialize_shards(rows: list[tuple]) -> list[dict[str, Any]]:
        return [{"shard_id": row[0], "min": row[1], "max": row[2]} for row in rows]

    @staticmethod
    def _serialize_placements(rows: list[tuple]) -> list[dict[str, Any]]:
        return [
            {
                "shard_id": row[0],
                "node": row[1],
                "port": row[2],
                "state": row[3],
            }
            for row in rows
        ]

    @staticmethod
    def _serialize_replica_counts(rows: list[tuple]) -> list[dict[str, int]]:
        return [{"shard_id": row[0], "replica_count": int(row[1])} for row in rows]
