Trade Events
============

.. note::
  For Python code documentation conventions and how to reference this file from code, see `.github/copilot-instructions.md`.


Overview
--------
Trade events are immutable, bi-temporal records. Each trade is stored once with
Book1 and Book2 on the same row, and positions are derived via aggregation.

Events are modeled as Python classes with a common base class, allowing type-safe
handling of event instances. When events are loaded from the database, a factory
function instantiates the correct event class based on the ``type_id``.

**References in Python code:**

- When documenting event-related logic in Python, include a `References:` section in the docstring pointing to this file (``docs/trade_events.rst``).

Example::

  References:
    See docs/trade_events.rst for event type definitions and semantics.


Event Class Hierarchy
---------------------
All event classes inherit from ``TradeEventBase`` and define their ``type_id`` as a class constant.

.. code-block:: python

  class TradeEventBase(BaseModel):
      """Base class for all trade events."""
      event_id: UUID
      book1_id: str
      book2_id: str
      book1_side: str  # 'BUY' or 'SELL'
      instrument_key: str
      quantity: float
      price: float
      currency: str  # 3-letter code
      non_economic_data: Dict[str, Any]
      valid_time: datetime  # Business time
      system_time: datetime  # System record time
      created_by: str
      type_id: int
      prior_event_id: Optional[UUID]


Event Types
-----------

**Constraint Validation**

The event class model enforces constraints at instantiation time using Pydantic field validators:

- **OpenEvent** (type_id=1): ``prior_event_id`` **must be None**.
  OpenEvents are standalone and represent initial trades with no prior reference.

- **CancelEvent** (type_id=2): ``prior_event_id`` **must be non-None**.
  CancelEvents always reference a prior event for compensating entry semantics.

- **NovationEvent** (type_id=5): ``prior_event_id`` **must be non-None**.
  NovationEvents always reference a prior event being novated.

Attempting to create an event with invalid constraint values will raise a Pydantic ``ValidationError``.


OpenEvent (type_id = 1)
  Books a new trade position between two counterparties.

  **Semantics:**
    - Records the initial agreement and execution of a trade.
    - Establishes a position for both book1 and book2.
    - Uses the traded quantity, price, and currency as recorded.

  **Constraints:**
    - ``prior_event_id`` must be None

  **Example Python class reference:**
    When handling OpenEvents, the system creates an instance of the ``OpenEvent`` class::

      event = OpenEvent(
          event_id=UUID(...),
          book1_id="ALPHA_TRADING",
          book2_id="BETA_CAPITAL",
          book1_side="BUY",
          instrument_key="AAPL",
          quantity=100.0,
          price=150.50,
          currency="USD",
          valid_time=datetime(...),
          system_time=datetime(...),
          created_by="trader1",
          type_id=1,
          non_economic_data={},
          prior_event_id=None
      )

CancelEvent (type_id = 2)
  Reverses the position effects of a prior OpenEvent.

  **Semantics:**
    - Creates a compensating entry that reverses an existing OpenEvent.
    - Reuses the original OpenEvent's economic fields (quantity, price, currency).
    - Applies inverse position impact: an original BUY becomes a SELL for position calculation,
      and quantities offset.
    - Both books see their positions reduced (or reversed) by the cancel amount.

  **Constraints:**
    - ``prior_event_id`` must reference a prior OpenEvent's UUID
    - The UI must select the prior trade; the server enforces the link

  **Example Python class reference:**
    A CancelEvent instance is created from a user request to cancel a trade::

      event = CancelEvent(
          event_id=UUID(...),
          book1_id="ALPHA_TRADING",
          book2_id="BETA_CAPITAL",
          book1_side="SELL",  # Opposite of original
          instrument_key="AAPL",
          quantity=100.0,  # Same as original
          price=150.50,  # Same as original
          currency="USD",  # Same as original
          valid_time=datetime(...),
          system_time=datetime(...),
          created_by="trader1",
          type_id=2,
          non_economic_data={},
          prior_event_id=UUID(...)  # Original OpenEvent ID
      )

NovationEvent (type_id = 5)
  Transfers the trade to a new counterparty.

  **Semantics:**
    - Replaces one party in an existing trade with a new counterparty.
    - Closes the original position and opens a new one with different parties.
    - Models contractual novation where one party is substituted out.

  **Constraints:**
    - ``prior_event_id`` references the prior event being novated
    - At least one of book1_id or book2_id differs from the prior event

  **Example Python class reference:**
    A NovationEvent replaces one side of an existing trade::

      event = NovationEvent(
          event_id=UUID(...),
          book1_id="ALPHA_TRADING",
          book2_id="GAMMA_PARTNERS",  # New counterparty
          book1_side="BUY",
          instrument_key="AAPL",
          quantity=100.0,
          price=150.50,
          currency="USD",
          valid_time=datetime(...),
          system_time=datetime(...),
          created_by="trader1",
          type_id=5,
          non_economic_data={},
          prior_event_id=UUID(...)  # Original OpenEvent ID
      )


Factory Function
----------------
When loading events from the database, use the ``create_trade_event`` factory function
to instantiate the correct event class::

  from app_abstract.models import create_trade_event

  event = create_trade_event({
      "event_id": UUID(...),
      "book1_id": "ALPHA",
      "book2_id": "BETA",
      "book1_side": "BUY",
      "instrument_key": "AAPL",
      "quantity": 100.0,
      "price": 150.50,
      "currency": "USD",
      "non_economic_data": {},
      "valid_time": datetime(...),
      "system_time": datetime(...),
      "created_by": "trader1",
      "type_id": 1,  # Determines which class is instantiated
      "prior_event_id": None,
  })
  # event is now an instance of OpenEvent


Cancel Behavior
---------------
When a CancelEvent is booked, the system:

1. **Reads the referenced OpenEvent** via the ``prior_event_id`` field.
2. **Uses original economic fields** (book1_id, book2_id, instrument_key, quantity, price, currency)
   for both the cancel row and position calculations.
3. **Applies inverse position effect**:
   - If the OpenEvent was a BUY, the CancelEvent is recorded as a SELL for position calculations.
   - If the OpenEvent was a SELL, the CancelEvent is recorded as a BUY for position calculations.
   - Both books' net positions decrease by the cancelled amount.
4. **Records the CancelEvent** with a reference to the original OpenEvent's ID and book1_id.

Notes
-----
- Trade events remain append-only; cancellations are new events, not mutations of existing ones.
- Position state is derived from the event log and should not be mutated directly.
- All event instances are Pydantic models and support serialization/deserialization.


Positions Query Path
--------------------
Positions are served through SQL function ``get_positions(p_book_id, p_valid_time, p_system_time)``
defined in ``sql/procs.sql``.

- The API endpoint ``GET /positions/{book_id}`` calls this function.
- Aggregation happens in PostgreSQL from ``trade_events`` (not from cached ``positions`` rows).
- Temporal filters are optional and are applied in SQL:

  - ``p_valid_time`` limits rows by ``valid_time <= p_valid_time``.
  - ``p_system_time`` limits rows by ``system_time <= p_system_time``.

This keeps the source of truth in one place and makes temporal position snapshots
consistent across API and direct SQL usage.


Position Effects (Change Ledger)
--------------------------------
The ``position_effects`` table is an immutable ledger of position deltas. Each trade event
generates four position effects (one per book per position type):

**Position Types:**

- **Shares**: Equity position quantity impact.
- **Proceeds**: Cash position impact (negative for buyer, positive for seller).

**Example:**
A BUY of 100 AAPL @ $150.50 between ALPHA_TRADING (buyer) and BETA_CAPITAL (seller)
generates:

1. ALPHA_TRADING, Shares (AAPL): +100
2. BETA_CAPITAL, Shares (AAPL): -100
3. ALPHA_TRADING, Proceeds (USD): -15,050
4. BETA_CAPITAL, Proceeds (USD): +15,050

**Access:**

- API endpoint: ``GET /position-effects`` (with optional ``?book_id=`` and ``?limit=`` filters)
- SQL table: ``position_effects`` in PostgreSQL (distributed by ``event_book1_id`` in Citus)

**Purpose:**

The position effects ledger is the source data for ``get_positions()``. Each position effect records
one booking (positive quantity) or reversal (negative quantity) of an economic exposure, making it
possible to reconstruct any historical position snapshot by summing effects up to a point in time.


