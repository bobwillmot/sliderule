"""Position effects calculation module.

This module contains business logic for calculating position deltas
(changes in Shares and Proceeds) for trade events.

Position effects are immutable ledger entries representing the economic
impact of each trade on both counterparties. The SQL layer only handles
insertion and aggregation; all delta calculations happen here.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PositionDeltas:
    """Position effect deltas for a single trade event.

    Each trade generates up to 8 position effects (4 per event type for regular trades,
    8 for novations that involve 3 books).
    """
    book1_shares_delta: Decimal
    book1_proceeds_delta: Decimal
    book2_shares_delta: Decimal
    book2_proceeds_delta: Decimal
    old_book2_shares_delta: Decimal = Decimal(0)
    old_book2_proceeds_delta: Decimal = Decimal(0)
    apply_book1: bool = True
    apply_book2: bool = True


def calculate_open_event_deltas(
    book1_side: str,
    quantity: Decimal,
    price: Decimal,
) -> PositionDeltas:
    """Calculate position deltas for an OpenEvent (new trade).

    An OpenEvent creates a new position between two counterparties.
    Book1 is the specified side (BUY or SELL); Book2 is the opposite side.

    Args:
        book1_side: 'BUY' or 'SELL' from the perspective of book1.
        quantity: Trade quantity (always positive).
        price: Price per unit.

    Returns:
        PositionDeltas with Shares and Proceeds for both books.

    Example (BUY 100 AAPL @ $150.50):
        - book1 (buyer): +100 Shares, -15,050 Proceeds
        - book2 (seller): -100 Shares, +15,050 Proceeds
    """
    # Determine the sign based on book1_side
    book1_sign = 1 if book1_side == "BUY" else -1
    effective_sign = book1_sign

    # Calculate Shares delta (quantity-based)
    book1_shares_delta = quantity * effective_sign
    book2_shares_delta = -book1_shares_delta

    # Calculate Proceeds delta (cash impact; negative for buyer, positive for seller)
    book1_proceeds_delta = -(quantity * price) * effective_sign
    book2_proceeds_delta = -book1_proceeds_delta

    return PositionDeltas(
        book1_shares_delta=book1_shares_delta,
        book1_proceeds_delta=book1_proceeds_delta,
        book2_shares_delta=book2_shares_delta,
        book2_proceeds_delta=book2_proceeds_delta,
        apply_book1=True,
        apply_book2=True,
    )


def calculate_cancel_event_deltas(
    book1_side: str,
    quantity: Decimal,
    price: Decimal,
) -> PositionDeltas:
    """Calculate position deltas for a CancelEvent (reversal of OpenEvent).

    A CancelEvent reverses a prior OpenEvent, reducing both books' positions
    back to their prior state. The reversal uses the opposite effective sign.

    Args:
        book1_side: Original 'BUY' or 'SELL' from the referenced OpenEvent.
        quantity: Original trade quantity.
        price: Original price.

    Returns:
        PositionDeltas with reversed (negated) deltas.

    Example (Cancel BUY 100 AAPL @ $150.50):
        - book1: -100 Shares (reversal), +15,050 Proceeds (cash in)
        - book2: +100 Shares (reversal), -15,050 Proceeds (cash out)
    """
    # For cancellation, reverse the effective sign
    book1_sign = 1 if book1_side == "BUY" else -1
    effective_sign = -book1_sign  # Negate to reverse the position

    # Calculate reversed Shares delta
    book1_shares_delta = quantity * effective_sign
    book2_shares_delta = -book1_shares_delta

    # Calculate reversed Proceeds delta
    book1_proceeds_delta = -(quantity * price) * effective_sign
    book2_proceeds_delta = -book1_proceeds_delta

    return PositionDeltas(
        book1_shares_delta=book1_shares_delta,
        book1_proceeds_delta=book1_proceeds_delta,
        book2_shares_delta=book2_shares_delta,
        book2_proceeds_delta=book2_proceeds_delta,
        apply_book1=True,
        apply_book2=True,
    )


def calculate_novation_event_deltas(
    book1_side: str,
    quantity: Decimal,
    price: Decimal,
) -> PositionDeltas:
    """Calculate position deltas for a NovationEvent (party substitution).

    A NovationEvent removes the old book2 from the trade and replaces it with
    a new book2. This generates 4 deltas for the old book2 (reversal) and
    4 new deltas for the new book2.

    Args:
        book1_side: Original 'BUY' or 'SELL' from the referenced OpenEvent.
        quantity: Original trade quantity.
        price: Original price.

    Returns:
        PositionDeltas with apply_book1=False, apply_book2=False (skip regular logic),
        and old_book2_* fields populated for the old party reversal.

    Example (Novate BUY 100 AAPL from original book2 to new_book2):
        - old_book2: -100 Shares (reversal), +15,050 Proceeds
        - new_book2: +100 Shares (new position), -15,050 Proceeds
    """
    book1_sign = 1 if book1_side == "BUY" else -1

    # Old book2 gets reversed (negated) deltas
    old_book2_shares_delta = quantity * book1_sign
    old_book2_proceeds_delta = -(quantity * price) * book1_sign

    return PositionDeltas(
        book1_shares_delta=Decimal(0),
        book1_proceeds_delta=Decimal(0),
        book2_shares_delta=Decimal(0),
        book2_proceeds_delta=Decimal(0),
        old_book2_shares_delta=old_book2_shares_delta,
        old_book2_proceeds_delta=old_book2_proceeds_delta,
        apply_book1=False,
        apply_book2=False,
    )
