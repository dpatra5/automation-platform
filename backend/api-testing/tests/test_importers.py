from __future__ import annotations

import json

import pytest

from apitest.importers import detect, import_content

OPENAPI = {
    "openapi": "3.0.3",
    "info": {"title": "Pets", "description": "Pet store"},
    "servers": [{"url": "https://{env}.pets.test/v1", "variables": {"env": {"default": "api"}}}],
    "components": {
        "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
        "schemas": {
            "Pet": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer", "example": 1},
                    "name": {"type": "string", "example": "Rex"},
                    "tag": {"type": "string", "nullable": True},
                },
            }
        },
        "parameters": {"Limit": {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}}},
    },
    "security": [{"bearerAuth": []}],
    "paths": {
        "/pets": {
            "get": {
                "summary": "List pets",
                "tags": ["pets"],
                "parameters": [{"$ref": "#/components/parameters/Limit"}],
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Pet"}}
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "createPet",
                "security": [],
                "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}},
                "responses": {"201": {"description": "created"}},
            },
        },
        "/pets/{petId}": {
            "parameters": [{"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}}],
            "delete": {"responses": {"204": {"description": "gone"}}},
        },
    },
}

POSTMAN = {
    "info": {"_postman_id": "x", "name": "PM", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{tok}}"}]},
    "variable": [{"key": "base", "value": "https://pm.test"}],
    "item": [
        {
            "name": "Users",
            "item": [
                {
                    "name": "Get user",
                    "event": [{"listen": "test", "script": {"exec": ["pm.test()"]}}],
                    "request": {
                        "method": "GET",
                        "url": {
                            "raw": "{{base}}/users/:id?verbose=1",
                            "query": [{"key": "verbose", "value": "1"}],
                            "variable": [{"key": "id", "value": ""}],
                        },
                        "header": [{"key": "Accept", "value": "application/json"}],
                    },
                }
            ],
        },
        {
            "name": "Create",
            "request": {
                "method": "POST",
                "url": "{{base}}/users",
                "auth": {"type": "noauth"},
                "body": {"mode": "raw", "raw": '{"a": 1}', "options": {"raw": {"language": "json"}}},
            },
        },
    ],
}


def test_detect() -> None:
    assert detect("curl https://x.test") == "curl"
    assert detect(json.dumps(OPENAPI)) == "openapi"
    assert detect("openapi: 3.0.0\npaths: {}\n") == "openapi"
    assert detect(json.dumps(POSTMAN)) == "postman"
    assert detect('{"format": "apitest-collection", "name": "x"}') == "native"
    with pytest.raises(ValueError):
        detect('{"hello": 1}')


def test_curl_bash_multiline() -> None:
    col = import_content(
        "curl -X POST 'https://api.test/items?debug=1' \\\n"
        "  -H 'Content-Type: application/json' -H 'X-Trace: 1' \\\n"
        "  --data-raw '{\"name\":\"a\"}' -k --compressed"
    )
    spec = col.requests[0].spec
    assert col.format == "curl" and col.requests[0].name == "POST /items"
    assert spec.method == "POST" and spec.url == "https://api.test/items"
    assert [(p.key, p.value) for p in spec.params] == [("debug", "1")]
    assert spec.body.mode == "json" and json.loads(spec.body.content) == {"name": "a"}
    assert spec.settings.verify_tls is False


def test_curl_form_basic_and_multiple_commands() -> None:
    col = import_content("curl https://a.test/login -u bob:pw -d user=bob -d x=1\ncurl --url=https://a.test/b")
    first, second = (r.spec for r in col.requests)
    assert first.method == "POST" and first.auth.type == "basic" and first.auth.password == "pw"
    assert first.body.mode == "form" and [(f.key, f.value) for f in first.body.form] == [("user", "bob"), ("x", "1")]
    assert second.method == "GET" and second.url == "https://a.test/b"


def test_curl_windows_cmd_escapes() -> None:
    col = import_content('curl ^"https://a.test/x^" ^\n  -H ^"Accept: */*^"')
    assert col.requests[0].spec.url == "https://a.test/x"
    assert col.requests[0].spec.headers[0].key == "Accept"


def test_openapi_import() -> None:
    col = import_content(json.dumps(OPENAPI))
    variables = {v.key: v for v in col.variables}
    assert variables["baseUrl"].value == "https://api.pets.test/v1"
    assert variables["token"].secret and "petId" in variables
    by_name = {r.name: r.spec for r in col.requests}
    listing = by_name["pets / List pets"]
    assert listing.url == "{{baseUrl}}/pets"
    assert listing.auth.type == "bearer" and listing.auth.token == "{{token}}"
    assert [(p.key, p.value, p.enabled) for p in listing.params] == [("limit", "20", False)]
    status, schema = listing.assertions
    assert status.expected == "200"
    inlined = json.loads(schema.expected)
    assert inlined["items"]["properties"]["tag"]["type"] == ["string", "null"]
    create = by_name["createPet"]
    assert create.auth.type == "none"
    assert json.loads(create.body.content) == {"id": 1, "name": "Rex", "tag": "string"}
    assert create.assertions[0].expected == "201"
    delete = by_name["DELETE /pets/{petId}"]
    assert delete.url == "{{baseUrl}}/pets/{{petId}}" and delete.method == "DELETE"


def test_swagger2_yaml_import() -> None:
    doc = """
swagger: "2.0"
info: {title: Legacy}
host: legacy.test
basePath: /api
schemes: [https]
paths:
  /login:
    post:
      parameters:
        - {name: body, in: body, schema: {type: object, properties: {user: {type: string, example: ann}}}}
      responses:
        200: {description: ok, schema: {type: object, properties: {token: {type: string}}}}
"""
    col = import_content(doc)
    assert col.variables[0].value == "https://legacy.test/api"
    spec = col.requests[0].spec
    assert json.loads(spec.body.content) == {"user": "ann"}
    assert spec.assertions[0].expected == "200" and spec.assertions[1].source == "json_schema"


def test_postman_import() -> None:
    col = import_content(json.dumps(POSTMAN))
    assert col.name == "PM" and col.variables[0].key == "base"
    get, create = (r.spec for r in col.requests)
    assert col.requests[0].name == "Users / Get user"
    assert get.url == "{{base}}/users/{{id}}"
    assert [(p.key, p.value) for p in get.params] == [("verbose", "1")]
    assert get.auth.type == "bearer" and get.auth.token == "{{tok}}"
    assert create.auth.type == "none" and create.body.mode == "json"
    assert any("test scripts" in w for w in col.warnings)


def test_native_roundtrip_validation() -> None:
    col = import_content(json.dumps({"format": "apitest-collection", "name": "N", "requests": [{"name": "r", "url": "x"}]}))
    assert col.requests[0].spec.url == "x"
    with pytest.raises(ValueError, match="invalid collection export"):
        import_content(json.dumps({"format": "apitest-collection", "name": "N", "requests": [{"name": ""}]}))
