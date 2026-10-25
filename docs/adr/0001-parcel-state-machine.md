
# ADR 0001: Keep Parcel Lifecycle Rules in the Domain Module

## Status

Accepted

## Context

The Tawseel API has several parcel events, including dispatch, delivery, failure, and return. Each event is only valid for certain parcel states, and the number of delivery attempts must not exceed the allowed limit. These rules need to be enforced consistently regardless of which API endpoint calls them.

## Decision

Keep the parcel lifecycle logic in the pure Python `app/domain.py` module and implement the rules in `apply_event()`. The function validates transitions and returns a new Parcel object without modifying the original. The FastAPI layer handles HTTP requests and translates domain errors into HTTP responses.

## Consequences

The lifecycle rules are centralized, easier to test independently, and not coupled to FastAPI or Pydantic. This separation makes future changes to the lifecycle easier to manage. However, the API layer must correctly handle `InvalidTransition` exceptions raised by the domain module.
