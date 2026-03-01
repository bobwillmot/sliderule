from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class TradeRequest(BaseModel):
    """
    Represents a request to book a trade event.

    Attributes:
        book1_id: The primary book/counterparty.
        book2_id: The secondary book/counterparty.
        book1_side: 'BUY' or 'SELL' from book1's perspective.
        instrument_key: The traded instrument.
        quantity: Trade quantity.
        price: Trade price.
        currency: 3-letter currency code.
        non_economic_data: Optional non-economic metadata.
        valid_time: Business time for the event.
        created_by: User who created the event.
        type_id: Event type (see docs/trade_events.rst).
        prior_event_id: Event id of prior event (if any).

    References:
        See docs/trade_events.rst for event type definitions and booking rules.
    """
    book1_id: str
    book2_id: str
    book1_side: str = Field(pattern="^(BUY|SELL)$")
    instrument_key: str
    quantity: float
    price: float
    currency: str = Field(min_length=3, max_length=3)
    non_economic_data: Optional[Dict[str, Any]] = None
    valid_time: datetime
    created_by: Optional[str] = None
    type_id: int = Field(ge=1, le=5)
    prior_event_id: Optional[UUID] = None

    @field_validator("type_id")
    @classmethod
    def validate_type_id(cls, value: int) -> int:
        if value not in (1, 2, 5):
            raise ValueError("type_id must be one of: 1 (OpenEvent), 2 (CancelEvent), 5 (NovationEvent)")
        return value

    @model_validator(mode="after")
    def validate_novation_book_constraint(self) -> "TradeRequest":
        """
        Validate novation-specific constraints.

        For NovationEvent (type_id=5):
        - new book2_id cannot be the same as book1_id
        - prior_event_id is required (enforced by NovationEvent model)

        Note: book2_id not being the same as prior book2_id is checked in the
        booking endpoint after fetching the prior event.

        References:
            See docs/trade_events.rst for novation constraints.
        """
        if self.type_id == 5:
            if self.book2_id == self.book1_id:
                raise ValueError(
                    "NovationEvent: new book2_id cannot be the same as book1_id"
                )
        return self


class TradeResponse(BaseModel):
    """
    Response model for a booked trade event.

    Attributes:
        event_id: The unique identifier for the booked event.
    """
    event_id: UUID


class ValidActionsResponse(BaseModel):
    """
    Response model for valid actions on a trade event.

    Attributes:
        can_cancel: Whether the trade can be cancelled.
        can_novate: Whether the trade can be novated.

    References:
        See docs/trade_events.rst for action constraints.
    """
    can_cancel: bool
    can_novate: bool


class TradeEventBase(BaseModel):
    """
    Base class for all trade events.

    Attributes:
        event_id: Unique event identifier.
        book1_id: Primary book/counterparty.
        book2_id: Secondary book/counterparty.
        book1_side: 'BUY' or 'SELL' from book1's perspective.
        instrument_key: The traded instrument.
        quantity: Trade quantity.
        price: Trade price.
        currency: 3-letter currency code.
        non_economic_data: Non-economic metadata.
        valid_time: Business time for the event.
        system_time: System time when the event was recorded.
        created_by: User who created the event.
        type_id: Event type identifier.
        prior_event_id: Event id of prior event (if any).

    References:
        See docs/trade_events.rst for event type definitions and semantics.
    """
    event_id: UUID
    book1_id: str
    book2_id: str
    book1_side: str
    instrument_key: str
    quantity: float
    price: float
    currency: str
    non_economic_data: Dict[str, Any]
    valid_time: datetime
    system_time: datetime
    created_by: str
    type_id: int
    prior_event_id: Optional[UUID] = None


class OpenEvent(TradeEventBase):
    """
    Opens a new trade position.

    An OpenEvent books a new trade between two books. This is the primary event
    type for recording initial trades. The event has no prior event reference.

    Attributes:
        Inherits all attributes from TradeEventBase.

    Constraints:
        - prior_event_id must be None

    References:
        See docs/trade_events.rst for OpenEvent semantics and booking rules.
    """
    type_id: int = 1

    @field_validator("prior_event_id")
    @classmethod
    def validate_no_prior_event(cls, value: Any) -> Any:
        if value is not None:
            raise ValueError("OpenEvent cannot have a prior event reference")
        return value


class CancelEvent(TradeEventBase):
    """
    Reverses the position effects of a prior OpenEvent.

    A CancelEvent creates a compensating entry that reverses the economic effects
    of a previously booked OpenEvent. The original OpenEvent's economic fields
    (quantity, price, currency) are reused for the cancel, but with inverted
    position impact for both books.

    Attributes:
        Inherits all attributes from TradeEventBase.

    Constraints:
        - prior_event_id must reference a prior OpenEvent
        - Uses original OpenEvent's economic fields for the reversal

    References:
        See docs/trade_events.rst for CancelEvent semantics and cancel behavior.
    """
    type_id: int = 2

    @field_validator("prior_event_id")
    @classmethod
    def validate_has_prior_event(cls, value: Any, info: Any) -> Any:
        if value is None:
            field_name = info.field_name
            raise ValueError(f"CancelEvent requires {field_name} to reference prior event")
        return value


class NovationEvent(TradeEventBase):
    """
    Transfers a trade to a new counterparty.

    A NovationEvent replaces one counterparty in an existing trade with a new
    counterparty. This models a novation where one party is substituted for
    another while keeping the economic terms intact.

    Attributes:
        Inherits all attributes from TradeEventBase.

    Constraints:
        - prior_event_id references the prior event being novated
        - Replaces one side of the trade with a new book

    References:
        See docs/trade_events.rst for NovationEvent semantics and novation rules.
    """
    type_id: int = 5

    @field_validator("prior_event_id")
    @classmethod
    def validate_has_prior_event(cls, value: Any, info: Any) -> Any:
        if value is None:
            field_name = info.field_name
            raise ValueError(f"NovationEvent requires {field_name} to reference prior event")
        return value


def create_trade_event(event_data: Dict[str, Any]) -> TradeEventBase:
    """
    Factory function to create the appropriate trade event subclass based on type_id.

    Args:
        event_data: Dictionary containing event fields including 'type_id'.

    Returns:
        An instance of OpenEvent, CancelEvent, or NovationEvent based on type_id.

    Raises:
        ValueError: If type_id is not recognized.

    References:
        See docs/trade_events.rst for event type definitions.
    """
    type_id = event_data.get("type_id")
    if type_id == 1:
        return OpenEvent(**event_data)
    elif type_id == 2:
        return CancelEvent(**event_data)
    elif type_id == 5:
        return NovationEvent(**event_data)
    else:
        raise ValueError(f"Unknown event type_id: {type_id}")


def get_valid_actions(event: TradeEventBase, has_cancel: bool = False, has_novation: bool = False) -> ValidActionsResponse:
    """
    Determine which actions are valid for a given trade event.

    An action is valid if:
    - The event is an active event (OpenEvent type_id == 1 or NovationEvent type_id == 5)
    - The event has not already been cancelled (no CancelEvent references it)
    - The event has not already been novated (no NovationEvent references it)

    Once a trade is cancelled or novated, it becomes locked and cannot be further modified.
    NovationEvents themselves become the new active trade and can be cancelled or novated again.

    Args:
        event: The trade event to check.
        has_cancel: Whether this event already has a CancelEvent referencing it.
        has_novation: Whether this event already has a NovationEvent referencing it.

    Returns:
        ValidActionsResponse with can_cancel and can_novate flags.

    References:
        See docs/trade_events.rst for event action constraints and novation locking.
    """
    is_active_event = event.type_id in (1, 5)  # OpenEvent or NovationEvent
    not_cancelled = not has_cancel
    not_novated = not has_novation

    # Only active events that haven't been cancelled or novated can be cancelled or novated
    # Cancelled or novated trades are locked and cannot be further modified
    can_perform_action = is_active_event and not_cancelled and not_novated

    return ValidActionsResponse(
        can_cancel=can_perform_action,
        can_novate=can_perform_action,
    )
