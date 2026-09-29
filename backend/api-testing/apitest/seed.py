"""First-start sample data: a chained demo collection and a matching environment."""

from __future__ import annotations

import json

from apitest.config import Settings
from apitest.db import Collection, Database, Environment, Meta, RequestItem
from apitest.demo import DEMO_PASSWORD, DEMO_USERNAME
from apitest.schemas import Assertion, Auth, Body, Extraction, RequestSpec, Variable

_PRODUCT_LIST_SCHEMA = {
    "type": "object",
    "required": ["items", "count"],
    "properties": {
        "count": {"type": "integer", "minimum": 0},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "price", "in_stock"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "price": {"type": "number", "exclusiveMinimum": 0},
                    "in_stock": {"type": "boolean"},
                },
            },
        },
    },
}

_BEARER = Auth(type="bearer", token="{{token}}")


def _status(code: str) -> Assertion:
    return Assertion(source="status", operator="equals", expected=code)


def demo_requests() -> list[tuple[str, RequestSpec]]:
    return [
        (
            "Login and capture token",
            RequestSpec(
                method="POST",
                url="{{baseUrl}}/auth/login",
                body=Body(mode="json", content='{\n  "username": "{{username}}",\n  "password": "{{password}}"\n}'),
                assertions=[
                    _status("200"),
                    Assertion(source="json", property="$.token", operator="exists"),
                    Assertion(source="response_time", operator="lt", expected="2000"),
                ],
                extractions=[Extraction(variable="token", source="json", property="$.token")],
                description="Logs in with the demo account and stores the bearer token for the next requests.",
            ),
        ),
        (
            "List products",
            RequestSpec(
                url="{{baseUrl}}/products",
                auth=_BEARER,
                assertions=[
                    _status("200"),
                    Assertion(source="json", property="$.count", operator="gt", expected="0"),
                    Assertion(source="json", property="$.items", operator="type_is", expected="array"),
                    Assertion(source="header", property="content-type", operator="contains", expected="json"),
                    Assertion(source="json_schema", expected=json.dumps(_PRODUCT_LIST_SCHEMA, indent=2)),
                ],
            ),
        ),
        (
            "Create product",
            RequestSpec(
                method="POST",
                url="{{baseUrl}}/products",
                auth=_BEARER,
                body=Body(mode="json", content='{\n  "name": "Widget {{$randomInt}}",\n  "price": 19.99\n}'),
                assertions=[
                    _status("201"),
                    Assertion(source="json", property="$.id", operator="exists"),
                    Assertion(source="json", property="$.price", operator="equals", expected="19.99"),
                ],
                extractions=[Extraction(variable="productId", source="json", property="$.id")],
            ),
        ),
        (
            "Get created product",
            RequestSpec(
                url="{{baseUrl}}/products/{{productId}}",
                auth=_BEARER,
                assertions=[
                    _status("2xx"),
                    Assertion(source="json", property="$.id", operator="equals", expected="{{productId}}"),
                    Assertion(source="json", property="$.name", operator="matches", expected="^Widget \\d+$"),
                ],
            ),
        ),
        (
            "Delete product",
            RequestSpec(method="DELETE", url="{{baseUrl}}/products/{{productId}}", auth=_BEARER, assertions=[_status("204")]),
        ),
        (
            "Deleted product returns 404",
            RequestSpec(
                url="{{baseUrl}}/products/{{productId}}",
                auth=_BEARER,
                assertions=[
                    _status("404"),
                    Assertion(source="json", property="$.detail", operator="equals", expected="product not found"),
                ],
            ),
        ),
        (
            "Rejects requests without a token",
            RequestSpec(url="{{baseUrl}}/products", assertions=[_status("401")]),
        ),
    ]


def seed_demo(db: Database, settings: Settings) -> None:
    with db.sessions() as session:
        if session.get(Meta, "seeded") is not None:
            return
        session.add(Meta(key="seeded", value="1"))
        env_vars = [
            Variable(key="baseUrl", value=f"http://127.0.0.1:{settings.port}/demo"),
            Variable(key="username", value=DEMO_USERNAME),
            Variable(key="password", value=DEMO_PASSWORD, secret=True),
        ]
        session.add(Environment(name="Local demo", variables=[v.model_dump() for v in env_vars]))
        collection = Collection(
            name="Demo Store API (sample)",
            description="End-to-end sample: login, chain the token and product id, CRUD and negative checks. "
            "Select the 'Local demo' environment and run it.",
            variables=[],
        )
        collection.requests = [
            RequestItem(name=name, position=i, spec=spec.model_dump(mode="json"))
            for i, (name, spec) in enumerate(demo_requests())
        ]
        session.add(collection)
        session.commit()
