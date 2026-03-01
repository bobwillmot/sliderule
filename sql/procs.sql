CREATE OR REPLACE FUNCTION create_book(p_name text)
RETURNS text AS $$
DECLARE
    v_id text;
BEGIN
    SELECT book_id INTO v_id FROM books WHERE book_name = p_name;
    IF v_id IS NULL THEN
        INSERT INTO books (book_id, book_name)
        VALUES (p_name, p_name)
        RETURNING book_id INTO v_id;
    END IF;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION create_instrument(p_key text, p_description text)
RETURNS text AS $$
BEGIN
    INSERT INTO instruments (instrument_key, description)
    VALUES (p_key, p_description)
    ON CONFLICT (instrument_key) DO UPDATE SET description = EXCLUDED.description;
    RETURN p_key;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION book_trade(
    p_book1_id text,
    p_book2_id text,
    p_book1_side text,
    p_instrument_key text,
    p_quantity numeric,
    p_price numeric,
    p_currency text,
    p_non_economic_data jsonb,
    p_valid_time timestamptz,
    p_created_by text,
    p_type_id integer,
    p_correction_of uuid DEFAULT NULL,
    p_book1_shares_delta numeric DEFAULT NULL,
    p_book1_proceeds_delta numeric DEFAULT NULL,
    p_book2_shares_delta numeric DEFAULT NULL,
    p_book2_proceeds_delta numeric DEFAULT NULL,
    p_old_book2_shares_delta numeric DEFAULT NULL,
    p_old_book2_proceeds_delta numeric DEFAULT NULL,
    p_apply_book1 boolean DEFAULT true,
    p_apply_book2 boolean DEFAULT true
)
RETURNS uuid AS $$
DECLARE
    v_event_id uuid;
    v_book1_id text;
    v_book2_id text;
    v_original_book2_id text;
    v_book1_side text;
    v_instrument_key text;
    v_quantity numeric;
    v_currency text;
    v_referenced_type_id integer;
    v_book1_shares_delta numeric;
    v_book2_shares_delta numeric;
    v_book1_proceeds_delta numeric;
    v_book2_proceeds_delta numeric;
    v_old_book2_shares_delta numeric;
    v_old_book2_proceeds_delta numeric;
BEGIN
    IF p_book1_id = p_book2_id THEN
        RAISE EXCEPTION 'Buy and sell books must differ';
    END IF;

    IF p_book1_side NOT IN ('BUY', 'SELL') THEN
        RAISE EXCEPTION 'book1_side must be BUY or SELL';
    END IF;

    IF p_type_id NOT IN (1, 2, 5) THEN
        RAISE EXCEPTION 'type_id must be 1 (OpenEvent), 2 (CancelEvent), or 5 (NovationEvent)';
    END IF;

    IF p_type_id = 1 THEN
        IF p_correction_of IS NOT NULL THEN
            RAISE EXCEPTION 'OpenEvent cannot reference a prior trade';
        END IF;

        v_book1_id := p_book1_id;
        v_book2_id := p_book2_id;
        v_book1_side := p_book1_side;
        v_instrument_key := p_instrument_key;
        v_quantity := p_quantity;
        v_currency := p_currency;
    ELSE
        IF p_correction_of IS NULL THEN
            RAISE EXCEPTION 'Non-open events require correction_of';
        END IF;

        SELECT book1_id,
               book2_id,
               book1_side,
               instrument_key,
               quantity,
               currency,
               type_id
        INTO v_book1_id,
             v_original_book2_id,
             v_book1_side,
             v_instrument_key,
             v_quantity,
             v_currency,
             v_referenced_type_id
        FROM trade_events
        WHERE event_id = p_correction_of
        LIMIT 1;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Referenced trade not found for cancellation';
        END IF;

        IF v_referenced_type_id NOT IN (1, 5) THEN
            RAISE EXCEPTION 'Only OpenEvents (type_id=1) and NovationEvents (type_id=5) can be cancelled or novated';
        END IF;

        IF p_book1_id <> v_book1_id THEN
            RAISE EXCEPTION 'Referenced trade book1_id mismatch';
        END IF;

        IF p_type_id = 2 AND p_book2_id <> v_original_book2_id THEN
            RAISE EXCEPTION 'book2_id must match referenced trade for CancelEvent';
        END IF;

        IF p_book1_side <> v_book1_side THEN
            RAISE EXCEPTION 'book1_side must match referenced trade';
        END IF;

        IF p_instrument_key <> v_instrument_key THEN
            RAISE EXCEPTION 'instrument_key must match referenced trade';
        END IF;

        IF p_currency <> v_currency THEN
            RAISE EXCEPTION 'currency must match referenced trade';
        END IF;

        IF p_type_id = 2 THEN
            v_book2_id := v_original_book2_id;
        ELSIF p_type_id = 5 THEN
            v_book2_id := p_book2_id;
            IF v_book2_id = v_original_book2_id THEN
                RAISE EXCEPTION 'NovationEvent requires a different book2_id';
            END IF;
        END IF;
    END IF;

    -- ARCHITECTURAL NOTE: Position effects are calculated in Python (app/positions.py)
    -- and passed as pre-calculated deltas to this function.
    -- SQL acts as a pure ledger: validation + insertion only. No business logic here.
    -- This ensures:
    --   * Position logic is testable independently of the database
    --   * Economic calculations are centralized in Python
    --   * SQL remains focused on durability and consistency
    --
    -- Delta parameters MUST be provided by the calling application (app/main.py).
    -- They represent the change in position for each book/instrument/position-type.
    IF p_book1_shares_delta IS NULL THEN
        RAISE EXCEPTION 'book1_shares_delta must be pre-calculated by application layer';
    END IF;

    v_book1_shares_delta := p_book1_shares_delta;
    v_book2_shares_delta := p_book2_shares_delta;
    v_book1_proceeds_delta := p_book1_proceeds_delta;
    v_book2_proceeds_delta := p_book2_proceeds_delta;
    v_old_book2_shares_delta := COALESCE(p_old_book2_shares_delta, 0);
    v_old_book2_proceeds_delta := COALESCE(p_old_book2_proceeds_delta, 0);

    INSERT INTO trade_events (
        book1_id,
        book2_id,
        book1_side,
        instrument_key,
        quantity,
        price,
        currency,
        non_economic_data,
        valid_time,
        created_by,
        type_id,
        correction_of
    ) VALUES (
        v_book1_id,
        v_book2_id,
        v_book1_side,
        v_instrument_key,
        v_quantity,
        p_price,
        v_currency,
        COALESCE(p_non_economic_data, '{}'::jsonb),
        p_valid_time,
        p_created_by,
        p_type_id,
        p_correction_of
    )
    RETURNING event_id INTO v_event_id;

    -- Insert position effects only if apply flags are true (regular trades)
    -- For novations, old and new book2 insertions happen separately below
    IF p_apply_book1 THEN
        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book1_id,
            v_instrument_key,
            'Shares',
            v_book1_shares_delta
        );

        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book1_id,
            v_currency,
            'Proceeds',
            v_book1_proceeds_delta
        );

    END IF;

    IF p_apply_book2 THEN
        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book2_id,
            v_instrument_key,
            'Shares',
            v_book2_shares_delta
        );

        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book2_id,
            v_currency,
            'Proceeds',
            v_book2_proceeds_delta
        );

    END IF;

    -- For NovationEvent: remove old book2, add new book2 position
    IF p_type_id = 5 THEN
        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_original_book2_id,
            v_instrument_key,
            'Shares',
            v_old_book2_shares_delta
        );

        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_original_book2_id,
            v_currency,
            'Proceeds',
            v_old_book2_proceeds_delta
        );

        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book2_id,
            v_instrument_key,
            'Shares',
            -v_old_book2_shares_delta
        );

        INSERT INTO position_effects (
            event_book1_id,
            event_id,
            book_id,
            instrument_key,
            position_type,
            quantity
        ) VALUES (
            v_book1_id,
            v_event_id,
            v_book2_id,
            v_currency,
            'Proceeds',
            -v_old_book2_proceeds_delta
        );

    END IF;

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;

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
) AS $$
BEGIN
    RETURN QUERY
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
    ORDER BY pe.position_type, pe.instrument_key;
END;
$$ LANGUAGE plpgsql;
