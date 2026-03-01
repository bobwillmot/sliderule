-- Shared reference/seed data for all database backends.

INSERT INTO books (book_id, book_name)
VALUES
    ('ALPHA_TRADING', 'ALPHA_TRADING'),
    ('BETA_CAPITAL', 'BETA_CAPITAL'),
    ('GAMMA_CAPITAL', 'GAMMA_CAPITAL'),
    ('DELTA_MARKETS', 'DELTA_MARKETS'),
    ('EPSILON_FUNDS', 'EPSILON_FUNDS'),
    ('ZETA_INVESTMENTS', 'ZETA_INVESTMENTS'),
    ('ETA_SECURITIES', 'ETA_SECURITIES'),
    ('THETA_TRADING', 'THETA_TRADING'),
    ('IOTA_ASSET_MGMT', 'IOTA_ASSET_MGMT'),
    ('KAPPA_GLOBAL', 'KAPPA_GLOBAL'),
    ('LAMBDA_HOLDINGS', 'LAMBDA_HOLDINGS'),
    ('MU_LIQUIDITY', 'MU_LIQUIDITY')
ON CONFLICT (book_id) DO UPDATE
SET book_name = EXCLUDED.book_name;

INSERT INTO trade_event_types (type_id, type_name)
VALUES
    (1, 'OpenEvent'),
    (2, 'CancelEvent'),
    (5, 'NovationEvent')
ON CONFLICT (type_id) DO UPDATE
SET type_name = EXCLUDED.type_name;

DELETE FROM trade_event_types
WHERE type_id IN (3, 4);

INSERT INTO instruments (instrument_key, description, exchange, last_close, last_close_date)
VALUES
    ('AAPL', 'Apple Inc.', 'NYSE', 185.25, DATE '2026-02-14'),
    ('MSFT', 'Microsoft Corporation', 'NYSE', 412.10, DATE '2026-02-14'),
    ('JPM', 'JPMorgan Chase & Co.', 'NYSE', 198.77, DATE '2026-02-14'),
    ('KO', 'The Coca-Cola Company', 'NYSE', 62.88, DATE '2026-02-14'),
    ('DIS', 'The Walt Disney Company', 'NYSE', 111.54, DATE '2026-02-14'),
    ('BA', 'The Boeing Company', 'NYSE', 209.31, DATE '2026-02-14'),
    ('XOM', 'Exxon Mobil Corporation', 'NYSE', 113.42, DATE '2026-02-14'),
    ('IBM', 'International Business Machines Corporation', 'NYSE', 201.06, DATE '2026-02-14'),
    ('MCD', 'McDonald''s Corporation', 'NYSE', 289.45, DATE '2026-02-14'),
    ('WMT', 'Walmart Inc.', 'NYSE', 170.12, DATE '2026-02-14')
ON CONFLICT (instrument_key) DO UPDATE
SET description = EXCLUDED.description,
    exchange = EXCLUDED.exchange,
    last_close = EXCLUDED.last_close,
    last_close_date = EXCLUDED.last_close_date;
