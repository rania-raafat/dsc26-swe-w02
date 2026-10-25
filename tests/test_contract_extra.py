
from fastapi.testclient import TestClient

from app.api import create_app


def make_client():
    return TestClient(create_app())


def create_parcel(client, ref="ORDER-1"):
    response = client.post(
        "/v1/parcels",
        json={
            "merchant_ref": ref,
            "cod_amount_piastres": 25000,
            "address_text": "Giza, Egypt",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_duplicate_merchant_ref_is_rejected():
    client = make_client()
    create_parcel(client, "DUP-1")

    response = client.post(
        "/v1/parcels",
        json={
            "merchant_ref": "DUP-1",
            "cod_amount_piastres": 100,
            "address_text": "Another address",
        },
    )

    assert response.status_code == 409
    listing = client.get("/v1/parcels").json()
    assert len(listing["items"]) == 1


def test_invalid_body_uses_problem_json():
    client = make_client()

    response = client.post(
        "/v1/parcels",
        json={
            "merchant_ref": "",
            "cod_amount_piastres": -1,
            "address_text": "",
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(
        "application/problem+json"
    )

    body = response.json()
    assert body["status"] == 422
    assert {"type", "title", "errors"} <= body.keys()

    invalid_fields = {tuple(error["loc"]) for error in body["errors"]}
    assert ("body", "merchant_ref") in invalid_fields
    assert ("body", "cod_amount_piastres") in invalid_fields
    assert ("body", "address_text") in invalid_fields


def test_three_attempts_are_enforced():
    client = make_client()
    parcel = create_parcel(client)

    def send_event(event_type):
        return client.post(
            f"/v1/parcels/{parcel['id']}/events",
            json={"type": event_type},
        )

    for attempt in range(3):
        dispatched = send_event("dispatch")
        assert dispatched.status_code == 200
        assert dispatched.json()["attempts"] == attempt + 1

        failed = send_event("fail")
        assert failed.status_code == 200

    rejected = send_event("dispatch")
    assert rejected.status_code == 409

    # The failed dispatch must not have changed the parcel.
    current = client.get(f"/v1/parcels/{parcel['id']}").json()
    assert current["state"] == "failed_attempt"
    assert current["attempts"] == 3

    returned = send_event("return")
    assert returned.status_code == 200
    assert returned.json()["state"] == "returned"


def test_pagination_walks_all_parcels():
    client = make_client()

    for i in range(57):
        create_parcel(client, f"PAGE-{i}")

    found_ids = []
    cursor = None

    while True:
        params = {"limit": 10}
        if cursor is not None:
            params["cursor"] = cursor

        response = client.get("/v1/parcels", params=params)
        assert response.status_code == 200

        body = response.json()
        found_ids.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]

        if cursor is None:
            break

    assert len(found_ids) == 57
    assert len(set(found_ids)) == 57


def test_cursor_survives_state_changes():
    client = make_client()
    parcels = [
        create_parcel(client, f"STATE-{i}")
        for i in range(25)
    ]

    first_page = client.get(
        "/v1/parcels",
        params={"state": "created", "limit": 10},
    ).json()

    assert len(first_page["items"]) == 10
    cursor = first_page["next_cursor"]
    assert cursor is not None

    # Change the state of all parcels on the first page.
    for parcel in first_page["items"]:
        response = client.post(
            f"/v1/parcels/{parcel['id']}/events",
            json={"type": "dispatch"},
        )
        assert response.status_code == 200

    # The next page must continue after the previous page's last item.
    next_page = client.get(
        "/v1/parcels",
        params={
            "state": "created",
            "limit": 10,
            "cursor": cursor,
        },
    )

    assert next_page.status_code == 200
    next_body = next_page.json()
    assert len(next_body["items"]) == 10
    assert all(item["state"] == "created" for item in next_body["items"])

    first_ids = {item["id"] for item in first_page["items"]}
    next_ids = {item["id"] for item in next_body["items"]}
    assert first_ids.isdisjoint(next_ids)


def test_invalid_cursor_returns_400():
    client = make_client()

    response = client.get(
        "/v1/parcels",
        params={"cursor": "not-a-real-cursor"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith(
        "application/problem+json"
    )


def test_openapi_operation_ids():
    client = make_client()
    schema = client.get("/openapi.json").json()

    expected = {
        ("/v1/parcels", "post"): "createParcel",
        ("/v1/parcels/{parcel_id}", "get"): "getParcel",
        ("/v1/parcels", "get"): "listParcels",
        ("/v1/parcels/{parcel_id}/events", "post"): "recordParcelEvent",
    }

    for (path, method), operation_id in expected.items():
        assert schema["paths"][path][method]["operationId"] == operation_id
