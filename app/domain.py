"""Parcel lifecycle rules for Tawseel.

Pure Python: do not import fastapi, starlette, pydantic or sqlalchemy here
(a hidden test checks). Keep the names below exactly as they are.
"""
from dataclasses import dataclass
from enum import StrEnum

MAX_ATTEMPTS = 3


class ParcelState(StrEnum):
    CREATED = "created"
    OUT_FOR_DELIVERY = "out_for_delivery"
    FAILED_ATTEMPT = "failed_attempt"
    DELIVERED = "delivered"
    RETURNED = "returned"


class EventType(StrEnum):
    DISPATCH = "dispatch"
    DELIVER = "deliver"
    FAIL = "fail"
    RETURN = "return"


class InvalidTransition(Exception): ...


@dataclass(frozen=True)
class Parcel:
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState = ParcelState.CREATED
    attempts: int = 0



def apply_event(parcel: Parcel, event: EventType) -> Parcel:
    """Return a new Parcel after applying a valid event."""
    new_state = parcel.state
    new_attempts = parcel.attempts

    if parcel.state == ParcelState.CREATED:
        if event == EventType.DISPATCH:
            new_state = ParcelState.OUT_FOR_DELIVERY
            new_attempts += 1
        else:
            raise InvalidTransition(
                f"Cannot apply {event} to {parcel.state}"
            )

    elif parcel.state == ParcelState.OUT_FOR_DELIVERY:
        if event == EventType.DELIVER:
            new_state = ParcelState.DELIVERED
        elif event == EventType.FAIL:
            new_state = ParcelState.FAILED_ATTEMPT
        else:
            raise InvalidTransition(
                f"Cannot apply {event} to {parcel.state}"
            )

    elif parcel.state == ParcelState.FAILED_ATTEMPT:
        if event == EventType.DISPATCH:
            if parcel.attempts >= MAX_ATTEMPTS:
                raise InvalidTransition("Maximum delivery attempts reached")

            new_state = ParcelState.OUT_FOR_DELIVERY
            new_attempts += 1

        elif event == EventType.RETURN:
            new_state = ParcelState.RETURNED

        else:
            raise InvalidTransition(
                f"Cannot apply {event} to {parcel.state}"
            )

    else:
        # DELIVERED and RETURNED are final states.
        raise InvalidTransition(
            f"Cannot apply {event} to final state {parcel.state}"
        )

    return Parcel(
        id=parcel.id,
        merchant_ref=parcel.merchant_ref,
        cod_amount_piastres=parcel.cod_amount_piastres,
        address_text=parcel.address_text,
        state=new_state,
        attempts=new_attempts,
    )
