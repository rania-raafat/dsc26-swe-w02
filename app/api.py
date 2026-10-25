
"""HTTP layer for the Tawseel parcel service."""

from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.domain import (
    EventType,
    InvalidTransition,
    Parcel,
    ParcelState,
    apply_event,
)


class ParcelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_ref: str = Field(min_length=1, max_length=64)
    cod_amount_piastres: int = Field(ge=0, le=5_000_000)
    address_text: str = Field(min_length=1, max_length=500)


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EventType


class ParcelOutput(BaseModel):
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState
    attempts: int


class ParcelListOutput(BaseModel):
    items: list[ParcelOutput]
    next_cursor: str | None


PROBLEM_SCHEMA = {
    "description": "Problem details response",
    "content": {
        "application/problem+json": {
            "schema": {
                "type": "object",
                "required": ["type", "title", "status"],
                "properties": {
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "status": {"type": "integer"},
                    "detail": {"type": "string"},
                    "errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["loc", "msg"],
                            "properties": {
                                "loc": {
                                    "type": "array",
                                    "items": {},
                                },
                                "msg": {"type": "string"},
                            },
                        },
                    },
                },
            }
        }
    },
}


def problem(
    status: int,
    title: str,
    detail: str,
    errors: list[dict] | None = None,
) -> JSONResponse:
    """Create a consistent application/problem+json response."""
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }

    if errors is not None:
        body["errors"] = errors

    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
    )


def parcel_to_dict(parcel: Parcel) -> dict:
    """Convert the domain parcel into the public JSON representation."""
    return {
        "id": parcel.id,
        "merchant_ref": parcel.merchant_ref,
        "cod_amount_piastres": parcel.cod_amount_piastres,
        "address_text": parcel.address_text,
        "state": parcel.state.value,
        "attempts": parcel.attempts,
    }


def create_app() -> FastAPI:
    """Create a new app with an independent in-memory store."""
    api = FastAPI(title="Tawseel Parcel API", version="1.0.0")

    # All mutable storage belongs to this app instance.
    store = {
        "parcels": {},
        "merchant_refs": set(),
        "order": [],
        "sequence": {},
        "next_sequence": 1,
        "cursors": {},
    }

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        # Return one error entry per invalid location.
        errors = []
        seen_locations = set()

        for error in exc.errors():
            location = list(error["loc"])
            location_key = tuple(location)

            if location_key in seen_locations:
                continue

            seen_locations.add(location_key)
            errors.append({
                "loc": location,
                "msg": error["msg"],
            })

        return problem(
            422,
            "Validation Error",
            "One or more request fields are invalid.",
            errors,
        )

    @api.post(
        "/v1/parcels",
        operation_id="createParcel",
        status_code=201,
        response_model=ParcelOutput,
        responses={
            409: PROBLEM_SCHEMA,
            422: PROBLEM_SCHEMA,
        },
    )
    def create_parcel(body: ParcelCreate):
        if body.merchant_ref in store["merchant_refs"]:
            return problem(
                409,
                "Conflict",
                "A parcel with this merchant_ref already exists.",
            )

        parcel = Parcel(
            id=f"pcl_{uuid4().hex}",
            merchant_ref=body.merchant_ref,
            cod_amount_piastres=body.cod_amount_piastres,
            address_text=body.address_text,
        )

        store["parcels"][parcel.id] = parcel
        store["merchant_refs"].add(parcel.merchant_ref)
        store["order"].append(parcel.id)

        store["sequence"][parcel.id] = store["next_sequence"]
        store["next_sequence"] += 1

        return JSONResponse(
            status_code=201,
            content=parcel_to_dict(parcel),
            headers={"Location": f"/v1/parcels/{parcel.id}"},
        )

    @api.get(
        "/v1/parcels/{parcel_id}",
        operation_id="getParcel",
        response_model=ParcelOutput,
        responses={
            404: PROBLEM_SCHEMA,
            422: PROBLEM_SCHEMA,
        },
    )
    def get_parcel(parcel_id: str):
        parcel = store["parcels"].get(parcel_id)

        if parcel is None:
            return problem(
                404,
                "Not Found",
                f"Parcel '{parcel_id}' was not found.",
            )

        return parcel_to_dict(parcel)

    @api.get(
        "/v1/parcels",
        operation_id="listParcels",
        response_model=ParcelListOutput,
        responses={
            400: PROBLEM_SCHEMA,
            422: PROBLEM_SCHEMA,
        },
    )
    def list_parcels(
        state: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
    ):
        selected_state = None

        if state is not None:
            try:
                selected_state = ParcelState(state)
            except ValueError:
                return problem(
                    422,
                    "Validation Error",
                    "The state query parameter is not valid.",
                    [{
                        "loc": ["query", "state"],
                        "msg": "Input should be a valid parcel state.",
                    }],
                )

        # A cursor must have been issued by this app instance.
        if cursor is not None:
            if cursor not in store["cursors"]:
                return problem(
                    400,
                    "Bad Request",
                    "The cursor is invalid or was not issued by this app.",
                )
            after_sequence = store["cursors"][cursor]
        else:
            after_sequence = 0

        matching = []

        # Scan in creation order. Sequence-based cursors remain stable
        # when earlier parcels change state between page requests.
        for parcel_id in store["order"]:
            sequence = store["sequence"][parcel_id]

            if sequence <= after_sequence:
                continue

            parcel = store["parcels"][parcel_id]

            if selected_state is not None and parcel.state != selected_state:
                continue

            matching.append(parcel)

        page = matching[:limit]
        has_more = len(matching) > limit

        next_cursor = None

        if has_more and page:
            last_parcel = page[-1]
            next_cursor = uuid4().hex
            store["cursors"][next_cursor] = store["sequence"][last_parcel.id]

        return {
            "items": [parcel_to_dict(parcel) for parcel in page],
            "next_cursor": next_cursor,
        }

    @api.post(
        "/v1/parcels/{parcel_id}/events",
        operation_id="recordParcelEvent",
        response_model=ParcelOutput,
        responses={
            404: PROBLEM_SCHEMA,
            409: PROBLEM_SCHEMA,
            422: PROBLEM_SCHEMA,
        },
    )
    def record_parcel_event(parcel_id: str, body: EventRequest):
        parcel = store["parcels"].get(parcel_id)

        if parcel is None:
            return problem(
                404,
                "Not Found",
                f"Parcel '{parcel_id}' was not found.",
            )

        try:
            updated_parcel = apply_event(parcel, body.type)
        except InvalidTransition as exc:
            return problem(
                409,
                "Conflict",
                str(exc),
            )

        # Save only after the transition succeeds.
        store["parcels"][parcel_id] = updated_parcel

        return parcel_to_dict(updated_parcel)

    return api


app = create_app()
