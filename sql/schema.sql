CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citus;

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

ALTER TABLE instruments
    ADD COLUMN IF NOT EXISTS exchange text NOT NULL DEFAULT 'NYSE';

ALTER TABLE instruments
    ADD COLUMN IF NOT EXISTS last_close numeric;

ALTER TABLE instruments
    ADD COLUMN IF NOT EXISTS last_close_date date;

CREATE TABLE IF NOT EXISTS trade_event_types (
    type_id integer PRIMARY KEY,
    type_name text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS trade_events (
    event_id uuid NOT NULL DEFAULT gen_random_uuid(),
    book1_id text NOT NULL,
    book2_id text NOT NULL,
    book1_side text NOT NULL CHECK (book1_side IN ('BUY', 'SELL')),
    instrument_key text NOT NULL,
    quantity numeric NOT NULL CHECK (quantity > 0),
    price numeric NOT NULL,
    currency text NOT NULL,
    non_economic_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_time timestamptz NOT NULL,
    system_time timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    type_id integer NOT NULL,
    event_type text NOT NULL DEFAULT 'TRADE',
    correction_of uuid NULL,
    CONSTRAINT trade_events_book_pair_chk CHECK (book1_id <> book2_id),
    CONSTRAINT trade_events_correction_chk CHECK (
        (type_id = 1 AND correction_of IS NULL)
        OR (type_id IN (2, 5) AND correction_of IS NOT NULL)
    ),
    CONSTRAINT trade_events_pk PRIMARY KEY (book1_id, event_id)
);

-- Citus limitation: foreign keys on distributed tables require shard_replication_factor=1.
-- Keep type_id as an entity table; enforce validity in application or procedures.

CREATE INDEX IF NOT EXISTS trade_events_book1_idx ON trade_events (book1_id, valid_time);
CREATE INDEX IF NOT EXISTS trade_events_book2_idx ON trade_events (book2_id, valid_time);
CREATE INDEX IF NOT EXISTS trade_events_instr_idx ON trade_events (instrument_key, valid_time);

CREATE TABLE IF NOT EXISTS position_effects (
    event_book1_id text NOT NULL,
    event_id uuid NOT NULL,
    book_id text NOT NULL,
    instrument_key text NOT NULL,
    position_type text NOT NULL CHECK (position_type IN ('Shares', 'Proceeds')),
    quantity numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS position_effects_book_idx
    ON position_effects (book_id, position_type, instrument_key);

-- Citus: replicate small dimension tables and shard trade events by book
SELECT create_reference_table('books');
SELECT create_reference_table('instruments');
SELECT create_reference_table('trade_event_types');
SELECT create_distributed_table('trade_events', 'book1_id');
SELECT create_distributed_table('position_effects', 'event_book1_id');
