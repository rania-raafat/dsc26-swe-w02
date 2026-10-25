
# ADR 0002: Use Cursor-Based Pagination

## Status

Accepted

## Context

The parcel list can grow over time, so returning every parcel in one response is not practical. Parcels can also change state between requests. With offset-based pagination, these changes can cause records to be skipped or repeated when filtering by state.

## Decision

Use cursor-based pagination for `listParcels`. Each parcel receives a sequence number when it is created, and each issued cursor records the sequence number of the last parcel returned on that page. The next request continues after that sequence number and applies the requested state filter to the current parcel states.

## Consequences

Cursor pagination supports walking through matching parcels without relying on a changing list position. It also allows the API to reject cursors that it did not issue. The implementation keeps sequence numbers and issued cursors in memory, so pagination state is lost when the app restarts, and the approach would need further design for persistent storage or multiple API instances.
