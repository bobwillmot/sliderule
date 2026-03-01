-- CockroachDB schema (no Citus extensions)
-- Compatible with CockroachDB 24+

CREATE TABLE IF NOT EXISTS books (
    book_id text PRIMARY KEY,
    book_name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS instruments (
    instrument_key text PRIMARY KEY,
    description text NOT NULL,
    exchange text NOT NULL DEFAULT 'NYSE',
    last_close numeric,
    last_close_date date
);

CREATE TABLE IF NOT EXISTS trade_event_types (
    type_id integer PRIMARY KEY,
    type_name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS trade_events (
    event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    book1_id text NOT NULL,
    book2_id text NOT NULL,
    book1_side text NOT NULL,
    instrument_key text NOT NULL,
    quantity numeric NOT NULL,
    price numeric NOT NULL,
    currency text NOT NULL,
    non_economic_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_time timestamptz NOT NULL,
    system_time timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    type_id integer NOT NULL,
    event_type text NOT NULL DEFAULT 'TRADE',
    correction_of uuid NULL,
    PRIMARY KEY (book1_id, event_id)
);

-- Check constraints
ALTER TABLE trade_events 
ADD CONSTRAINT trade_events_book_pair_chk CHECK (book1_id <> book2_id);

ALTER TABLE trade_events 
ADD CONSTRAINT trade_events_book1_side_chk CHECK (book1_side IN ('BUY', 'SELL'));

ALTER TABLE trade_events 
ADD CONSTRAINT trade_events_quantity_chk CHECK (quantity > 0);

ALTER TABLE trade_events 
ADD CONSTRAINT trade_events_correction_chk CHECK (
    (type_id = 1 AND correction_of IS NULL)
    OR (type_id IN (2, 5) AND correction_of IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS trade_events_book1_idx ON trade_events (book1_id, valid_time);
CREATE INDEX IF NOT EXISTS trade_events_book2_idx ON trade_events (book2_id, valid_time);
CREATE INDEX IF NOT EXISTS trade_events_instr_idx ON trade_events (instrument_key, valid_time);
CREATE INDEX IF NOT EXISTS trade_events_type_idx ON trade_events (type_id);

CREATE TABLE IF NOT EXISTS position_effects (
    event_book1_id text NOT NULL,
    event_id uuid NOT NULL,
    book_id text NOT NULL,
    instrument_key text NOT NULL,
    position_type text NOT NULL,
    quantity numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE position_effects 
ADD CONSTRAINT position_effects_type_chk CHECK (position_type IN ('Shares', 'Proceeds'));

CREATE INDEX IF NOT EXISTS position_effects_book_idx
    ON position_effects (book_id, position_type, instrument_key);
CREATE INDEX IF NOT EXISTS position_effects_event_idx
    ON position_effects (event_book1_id, event_id);

CREATE OR REPLACE FUNCTION get_positions(
    p_book_id text,
    p_valid_time timestamptz DEFAULT NULL,
    p_system_time timestamptz DEFAULT NULL
)
RETURNS TABLE (
    instrument_key text,
    position_type text,
    quantity numeric,
    valid_time timestamptz
)
LANGUAGE SQL
AS $$
    SELECT
        pe.instrument_key,
        pe.position_type,
        SUM(pe.quantity) AS quantity,
        MAX(te.valid_time) AS valid_time
    FROM position_effects pe
    JOIN trade_events te
      ON te.book1_id = pe.event_book1_id
     AND te.event_id = pe.event_id
    WHERE pe.book_id = p_book_id
      AND (p_valid_time IS NULL OR te.valid_time <= p_valid_time)
      AND (p_system_time IS NULL OR te.system_time <= p_system_time)
    GROUP BY pe.instrument_key, pe.position_type
    ORDER BY pe.position_type, pe.instrument_key
$$;
