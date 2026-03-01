CREATE EXTENSION IF NOT EXISTS citus;

DO $$
DECLARE
	attempt int;
BEGIN
	FOR attempt IN 1..30 LOOP
		BEGIN
			IF NOT EXISTS (
				SELECT 1
				FROM citus_get_active_worker_nodes()
				WHERE node_name = 'worker1'
			) THEN
				PERFORM citus_add_node('worker1', 5432);
			END IF;
			IF NOT EXISTS (
				SELECT 1
				FROM citus_get_active_worker_nodes()
				WHERE node_name = 'worker2'
			) THEN
				PERFORM citus_add_node('worker2', 5432);
			END IF;
			EXIT;
		EXCEPTION WHEN OTHERS THEN
			PERFORM pg_sleep(1);
		END;
	END LOOP;
END $$;

-- Set default replication factor for shards
ALTER SYSTEM SET citus.shard_replication_factor = 2;
SELECT pg_reload_conf();
