"""Import collections from cURL, OpenAPI/Swagger, Postman v2.x, or native exports."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import yaml
from pydantic import ValidationError

from apitest.schemas import (
    METHODS,
    Assertion,
    Auth,
    Body,
    CollectionExport,
    KeyValue,
    RequestSettings,
    RequestSpec,
    Variable,
)

NATIVE_FORMAT = "apitest-collection"
_HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
_PATH_PARAM = re.compile(r"\{([^{}]+)\}")


@dataclass
class ImportedRequest:
    name: str
    spec: RequestSpec


@dataclass
class ImportedCollection:
    format: str
    name: str
    description: str = ""
    variables: list[Variable] = field(default_factory=list)
    requests: list[ImportedRequest] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_content(content: str, fmt: str = "auto") -> ImportedCollection:
    text = content.strip()
    if fmt == "auto":
        fmt = detect(text)
    if fmt == "curl":
        col = import_curl(text)
    else:
        doc = _load_document(text)
        if not isinstance(doc, dict):
            raise ValueError("document must be a JSON or YAML object")
        importer = {"openapi": import_openapi, "postman": import_postman, "native": import_native}.get(fmt)
        if importer is None:
            raise ValueError(f"unknown format {fmt!r}")
        col = importer(doc)
    col.warnings = list(dict.fromkeys(col.warnings))
    return col


def detect(text: str) -> str:
    if re.match(r"curl(\.exe)?\s", text, re.IGNORECASE):
        return "curl"
    doc = _load_document(text)
    if isinstance(doc, dict):
        if "openapi" in doc or "swagger" in doc:
            return "openapi"
        info = doc.get("info")
        if isinstance(info, dict) and (
            "_postman_id" in info or "getpostman.com" in str(info.get("schema", ""))
        ):
            return "postman"
        if doc.get("format") == NATIVE_FORMAT:
            return "native"
    raise ValueError(
        "could not detect the format; expected a cURL command, OpenAPI/Swagger, "
        "Postman v2.x collection, or an exported collection"
    )


def _load_document(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"content is not valid JSON or YAML: {exc}") from exc


# --- helpers --------------------------------------------------------------------


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _clip(name: str) -> str:
    name = " ".join(str(name).split()) or "Untitled request"
    return name[:200]


def _split_url(url: str) -> tuple[str, list[KeyValue]]:
    if "?" not in url:
        return url, []
    base, _, rest = url.partition("?")
    query, hash_sign, fragment = rest.partition("#")
    params = [KeyValue(key=k, value=v) for k, v in parse_qsl(query, keep_blank_values=True)]
    return base + hash_sign + fragment, params


def _name_from_url(method: str, url: str) -> str:
    path = urlsplit(url).path if "://" in url else url
    return f"{method} {path or '/'}"


def _looks_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return False
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def _pretty(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2)
    except ValueError:
        return text


def _status_ok() -> list[Assertion]:
    return [Assertion(source="status", operator="lt", expected="400")]


# --- cURL -----------------------------------------------------------------------

_CURL_ARG_OPTIONS = {
    "-o", "--output", "-m", "--max-time", "--connect-timeout", "-w", "--write-out",
    "-x", "--proxy", "--cacert", "--cert", "-E", "--key", "--resolve", "--retry",
    "-T", "--upload-file", "-r", "--range", "-c", "--cookie-jar", "--limit-rate",
}  # fmt: skip


def import_curl(text: str) -> ImportedCollection:
    # Join bash (\), cmd (^) and PowerShell (`) line continuations.
    text = re.sub(r"[\\^`]\r?\n", " ", text)
    commands = [c for c in re.split(r"\n\s*(?=curl(?:\.exe)?\s)", text.strip(), flags=re.I) if c.strip()]
    col = ImportedCollection(format="curl", name="Imported from cURL")
    for command in commands:
        name, spec = _parse_curl(command, col.warnings)
        col.requests.append(ImportedRequest(name=name, spec=spec))
    if len(col.requests) == 1:
        col.name = col.requests[0].name
    return col


def _parse_curl(command: str, warnings: list[str]) -> tuple[str, RequestSpec]:
    if '^"' in command:  # Chrome's "Copy as cURL (cmd)" escapes with ^
        command = re.sub(r"\^(.)", r"\1", command)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(f"could not parse cURL command: {exc}") from exc
    if not tokens or tokens[0].lower() not in ("curl", "curl.exe"):
        raise ValueError("cURL import expects commands that start with 'curl'")

    method: str | None = None
    url: str | None = None
    headers: list[KeyValue] = []
    data: list[str] = []
    auth = Auth()
    options = RequestSettings()
    get_mode = json_flag = False

    i = 1
    while i < len(tokens):
        token = tokens[i]
        inline: str | None = None
        if token.startswith("--") and "=" in token:
            token, _, inline = token.partition("=")

        def arg() -> str:
            nonlocal i
            if inline is not None:
                return inline
            i += 1
            if i >= len(tokens):
                raise ValueError(f"cURL option {token} needs a value")
            return tokens[i]

        if token in ("-X", "--request"):
            method = arg().upper()
        elif token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
        elif token in ("-H", "--header"):
            key, _, value = arg().partition(":")
            if key.strip():
                headers.append(KeyValue(key=key.strip(), value=value.strip()))
        elif token in ("-d", "--data", "--data-raw", "--data-ascii", "--data-binary", "--data-urlencode"):
            value = arg()
            if value.startswith("@") and token != "--data-raw":
                warnings.append("cURL @file data references are not supported; paste the body instead")
            data.append(value)
        elif token == "--json":
            data.append(arg())
            json_flag = True
        elif token in ("-u", "--user"):
            user, _, password = arg().partition(":")
            auth = Auth(type="basic", username=user, password=password)
        elif token == "--url":
            url = arg()
        elif token in ("-k", "--insecure"):
            options.verify_tls = False
        elif token in ("-G", "--get"):
            get_mode = True
        elif token in ("-b", "--cookie"):
            headers.append(KeyValue(key="Cookie", value=arg()))
        elif token in ("-A", "--user-agent"):
            headers.append(KeyValue(key="User-Agent", value=arg()))
        elif token in ("-e", "--referer"):
            headers.append(KeyValue(key="Referer", value=arg()))
        elif token in ("-F", "--form"):
            arg()
            warnings.append("multipart form fields (-F) are not supported and were skipped")
        elif token in _CURL_ARG_OPTIONS:
            arg()
        elif token.startswith("-"):
            pass  # boolean flags such as -s, -v, -i, -L, --compressed
        elif url is None:
            url = token
        i += 1

    if not url:
        raise ValueError("cURL command has no URL")
    base, params = _split_url(url)
    body = Body()
    ctype = next((h.value.lower() for h in headers if h.key.lower() == "content-type"), "")
    if data:
        joined = "&".join(data)
        if get_mode:
            params += [KeyValue(key=k, value=v) for k, v in parse_qsl(joined, keep_blank_values=True)]
        else:
            if json_flag and not ctype:
                headers.append(KeyValue(key="Content-Type", value="application/json"))
                ctype = "application/json"
            if "json" in ctype or (not ctype and _looks_json(joined)):
                body = Body(mode="json", content=_pretty(joined))
            elif "xml" in ctype:
                body = Body(mode="xml", content=joined)
            elif "x-www-form-urlencoded" in ctype or (not ctype and "=" in joined):
                pairs = parse_qsl(joined, keep_blank_values=True)
                body = Body(mode="form", form=[KeyValue(key=k, value=v) for k, v in pairs])
            else:
                body = Body(mode="text", content=joined)
    method = method or ("POST" if data and not get_mode else "GET")
    if method not in METHODS:
        raise ValueError(f"unsupported HTTP method {method!r}")
    spec = RequestSpec(
        method=method,  # type: ignore[arg-type]
        url=base,
        params=params,
        headers=headers,
        body=body,
        auth=auth,
        settings=options,
        assertions=_status_ok(),
    )
    return _clip(_name_from_url(method, base)), spec


# --- OpenAPI / Swagger ------------------------------------------------------------


class _TooDeep(Exception):
    pass


class _Resolver:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc

    def ref(self, node: Any) -> Any:
        seen: set[str] = set()
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
                return {}
            seen.add(ref)
            node = self._lookup(ref)
        return node

    def _lookup(self, ref: str) -> Any:
        current: Any = self.doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict) or part not in current:
                return {}
            current = current[part]
        return current

    def schema(self, node: Any, depth: int = 0) -> Any:
        """Inline ``$ref``s and convert OpenAPI 3.0 quirks into plain JSON Schema."""
        if depth > 12:
            raise _TooDeep
        node = self.ref(node)
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in ("properties", "patternProperties") and isinstance(value, dict):
                out[key] = {k: self.schema(v, depth + 1) for k, v in value.items()}
            elif key in ("items", "additionalProperties", "not") and isinstance(value, dict):
                out[key] = self.schema(value, depth + 1)
            elif key in ("items", "allOf", "anyOf", "oneOf") and isinstance(value, list):
                out[key] = [self.schema(v, depth + 1) for v in value]
            elif key in ("nullable", "example", "xml", "externalDocs", "discriminator") or key.startswith("x-"):
                continue
            else:
                out[key] = value
        for bound in ("Minimum", "Maximum"):
            flag = out.get(f"exclusive{bound}")
            if isinstance(flag, bool):
                limit = out.pop(bound.lower(), None)
                out.pop(f"exclusive{bound}")
                if flag and limit is not None:
                    out[f"exclusive{bound}"] = limit
                elif limit is not None:
                    out[bound.lower()] = limit
        if node.get("nullable") is True or node.get("x-nullable") is True:
            kind = out.get("type")
            if isinstance(kind, str):
                out["type"] = [kind, "null"]
            if isinstance(out.get("enum"), list) and None not in out["enum"]:
                out["enum"] = [*out["enum"], None]
        return out

    def sample(self, node: Any, depth: int = 0) -> Any:
        node = self.ref(node)
        if not isinstance(node, dict) or depth > 8:
            return None
        for key in ("example", "default"):
            if key in node:
                return node[key]
        if node.get("enum"):
            return node["enum"][0]
        if isinstance(node.get("allOf"), list):
            merged: dict[str, Any] = {}
            for part in node["allOf"]:
                value = self.sample(part, depth + 1)
                if isinstance(value, dict):
                    merged.update(value)
            return merged
        for key in ("oneOf", "anyOf"):
            if isinstance(node.get(key), list) and node[key]:
                return self.sample(node[key][0], depth + 1)
        kind = node.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), None)
        if kind == "object" or "properties" in node:
            props = node.get("properties") or {}
            return {k: self.sample(v, depth + 1) for k, v in props.items()}
        if kind == "array":
            item = self.sample(node.get("items") or {}, depth + 1)
            return [item] if item is not None else []
        if kind in ("integer", "number"):
            return 0
        if kind == "boolean":
            return True
        if kind == "string":
            return {
                "date-time": "2024-01-01T00:00:00Z",
                "date": "2024-01-01",
                "email": "user@example.com",
                "uuid": "00000000-0000-0000-0000-000000000000",
                "uri": "https://example.com",
            }.get(str(node.get("format")), "string")
        return None


def _openapi_base_url(doc: dict[str, Any], warnings: list[str]) -> str:
    if "swagger" in doc:
        host = doc.get("host")
        base_path = str(doc.get("basePath") or "")
        schemes = doc.get("schemes") or ["https"]
        url = f"{schemes[0]}://{host}{base_path}" if host else base_path
    else:
        servers = doc.get("servers") or []
        url = ""
        if servers and isinstance(servers[0], dict):
            url = str(servers[0].get("url") or "")
            for name, var in (servers[0].get("variables") or {}).items():
                url = url.replace("{" + name + "}", str((var or {}).get("default", "")))
    url = url.rstrip("/")
    if not url.startswith(("http://", "https://")):
        warnings.append("the spec has no absolute server URL; set the baseUrl collection variable")
        url = f"http://localhost{url if url.startswith('/') else ''}"
    return url


def _add_variable(variables: list[Variable], key: str, value: str = "", secret: bool = False) -> None:
    if not any(v.key == key for v in variables):
        variables.append(Variable(key=key, value=value, secret=secret))


def _auth_for(security: Any, schemes: dict[str, Any], variables: list[Variable]) -> Auth:
    if not isinstance(security, list):
        return Auth()
    for requirement in security:
        if not isinstance(requirement, dict):
            continue
        for name in requirement:
            scheme = schemes.get(name)
            if not isinstance(scheme, dict):
                continue
            kind = scheme.get("type")
            http_scheme = str(scheme.get("scheme", "")).lower()
            if (kind == "http" and http_scheme == "bearer") or kind in ("oauth2", "openIdConnect"):
                _add_variable(variables, "token", secret=True)
                return Auth(type="bearer", token="{{token}}")
            if (kind == "http" and http_scheme == "basic") or kind == "basic":
                _add_variable(variables, "username")
                _add_variable(variables, "password", secret=True)
                return Auth(type="basic", username="{{username}}", password="{{password}}")
            if kind == "apiKey" and scheme.get("in") in ("header", "query"):
                _add_variable(variables, "apiKey", secret=True)
                return Auth(
                    type="api_key",
                    key=str(scheme.get("name") or "X-API-Key"),
                    value="{{apiKey}}",
                    location=scheme["in"],
                )
    return Auth()


def _param_example(res: _Resolver, param: dict[str, Any]) -> str:
    if "example" in param:
        return _to_str(param["example"])
    examples = param.get("examples")
    if isinstance(examples, dict) and examples:
        first = res.ref(next(iter(examples.values())))
        if isinstance(first, dict) and "value" in first:
            return _to_str(first["value"])
    schema = param.get("schema") if "schema" in param else param
    value = res.sample(schema)
    return "" if value is None or value == "string" else _to_str(value)


def _merge_params(res: _Resolver, *groups: Any) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        for raw in group or []:
            param = res.ref(raw)
            if isinstance(param, dict) and param.get("name"):
                merged[(str(param["name"]), str(param.get("in")))] = param
    return list(merged.values())


def _json_body(value: Any) -> Body:
    content = json.dumps(value, indent=2, default=str) if value is not None else "{}"
    return Body(mode="json", content=content)


def _apply_request_body(res: _Resolver, raw: Any, spec: RequestSpec, warnings: list[str]) -> None:
    body = res.ref(raw)
    if not isinstance(body, dict):
        return
    content = body.get("content") or {}
    for media, media_type in content.items():
        media_type = media_type or {}
        if "json" in media:
            example = media_type.get("example")
            examples = media_type.get("examples")
            if example is None and isinstance(examples, dict) and examples:
                first = res.ref(next(iter(examples.values())))
                example = first.get("value") if isinstance(first, dict) else None
            if example is None:
                example = res.sample(media_type.get("schema") or {})
            spec.body = _json_body(example)
            return
        if "x-www-form-urlencoded" in media:
            sample = res.sample(media_type.get("schema") or {})
            pairs = sample.items() if isinstance(sample, dict) else []
            fields = [KeyValue(key=k, value=_to_str(v)) for k, v in pairs]
            spec.body = Body(mode="form", form=fields)
            return
        if "xml" in media:
            spec.body = Body(mode="xml")
            return
        if media.startswith("text/"):
            spec.body = Body(mode="text")
            return
    if content:
        warnings.append(
            f"{spec.method} {spec.url}: body type(s) {', '.join(content)} are not supported; body left empty"
        )


def _add_response_assertions(
    res: _Resolver, responses: Any, spec: RequestSpec, swagger2: bool
) -> None:
    by_code = {str(k): v for k, v in (responses or {}).items()} if isinstance(responses, dict) else {}
    success = next((c for c in by_code if re.fullmatch(r"2\d\d", c)), None)
    spec.assertions.append(Assertion(source="status", operator="equals", expected=success or "2xx"))
    if success is None:
        return
    response = res.ref(by_code[success])
    if not isinstance(response, dict):
        return
    schema = None
    if swagger2:
        schema = response.get("schema")
    else:
        for media, media_type in (response.get("content") or {}).items():
            if "json" in media and isinstance(media_type, dict):
                schema = media_type.get("schema")
                break
    if not schema:
        return
    try:
        inlined = res.schema(schema)
    except _TooDeep:
        return  # recursive schemas are skipped rather than approximated
    spec.assertions.append(
        Assertion(source="json_schema", expected=json.dumps(inlined, indent=2, default=str))
    )


def import_openapi(doc: dict[str, Any]) -> ImportedCollection:
    res = _Resolver(doc)
    swagger2 = "swagger" in doc
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    col = ImportedCollection(
        format="openapi",
        name=_clip(str(info.get("title") or "Imported API")),
        description=str(info.get("description") or ""),
    )
    col.variables.append(Variable(key="baseUrl", value=_openapi_base_url(doc, col.warnings)))
    components = doc.get("components") if isinstance(doc.get("components"), dict) else {}
    schemes = components.get("securitySchemes") or doc.get("securityDefinitions") or {}
    global_security = doc.get("security")

    paths = doc.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("the OpenAPI document has no paths")
    for path, raw_item in paths.items():
        item = res.ref(raw_item)
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            spec = RequestSpec(
                method=method.upper(),  # type: ignore[arg-type]
                url="{{baseUrl}}" + _PATH_PARAM.sub(r"{{\1}}", str(path)),
                description=str(op.get("description") or op.get("summary") or ""),
            )
            for param in _merge_params(res, item.get("parameters"), op.get("parameters")):
                name, location = str(param["name"]), param.get("in")
                example = _param_example(res, param)
                if location == "path":
                    _add_variable(col.variables, name, example)
                elif location == "query":
                    spec.params.append(KeyValue(key=name, value=example, enabled=bool(param.get("required"))))
                elif location == "header" and name.lower() not in ("authorization", "content-type", "accept"):
                    spec.headers.append(KeyValue(key=name, value=example, enabled=bool(param.get("required"))))
                elif location == "body":
                    spec.body = _json_body(res.sample(param.get("schema") or {}))
                elif location == "formData":
                    if spec.body.mode != "form":
                        spec.body = Body(mode="form")
                    spec.body.form.append(KeyValue(key=name, value=example))
            if not swagger2:
                _apply_request_body(res, op.get("requestBody"), spec, col.warnings)
            spec.auth = _auth_for(op.get("security", global_security), schemes, col.variables)
            _add_response_assertions(res, op.get("responses"), spec, swagger2)
            name = op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"
            tags = op.get("tags")
            if isinstance(tags, list) and tags:
                name = f"{tags[0]} / {name}"
            col.requests.append(ImportedRequest(name=_clip(name), spec=spec))
    if not col.requests:
        raise ValueError("the OpenAPI document has no operations")
    return col


# --- Postman ----------------------------------------------------------------------


def _pm_description(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("content") or "")
    return str(value or "")


def _pm_auth(auth: Any) -> Auth:
    if not isinstance(auth, dict):
        return Auth()
    kind = auth.get("type")
    entries = auth.get(kind)

    def val(key: str) -> str:
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("key") == key:
                    return _to_str(entry.get("value"))
        elif isinstance(entries, dict):
            return _to_str(entries.get(key))
        return ""

    if kind == "bearer":
        return Auth(type="bearer", token=val("token"))
    if kind == "basic":
        return Auth(type="basic", username=val("username"), password=val("password"))
    if kind == "apikey":
        return Auth(
            type="api_key",
            key=val("key") or "X-API-Key",
            value=val("value"),
            location="query" if val("in") == "query" else "header",
        )
    return Auth()


def _pm_body(body: Any, warnings: list[str]) -> Body:
    if not isinstance(body, dict):
        return Body()
    mode = body.get("mode")
    if mode == "raw":
        raw = str(body.get("raw") or "")
        language = ((body.get("options") or {}).get("raw") or {}).get("language", "")
        if language == "json" or _looks_json(raw):
            return Body(mode="json", content=raw)
        if language == "xml":
            return Body(mode="xml", content=raw)
        return Body(mode="text", content=raw)
    if mode in ("urlencoded", "formdata"):
        fields: list[KeyValue] = []
        for entry in body.get(mode) or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "file":
                warnings.append(f"file field {entry.get('key')!r} was skipped")
                continue
            fields.append(
                KeyValue(
                    key=str(entry.get("key") or ""),
                    value=_to_str(entry.get("value")),
                    enabled=not entry.get("disabled", False),
                )
            )
        if mode == "formdata":
            warnings.append("multipart form-data bodies are sent as URL-encoded forms")
        return Body(mode="form", form=fields)
    if mode == "graphql":
        gql = body.get("graphql") or {}
        variables: Any = gql.get("variables") or {}
        if isinstance(variables, str):
            try:
                variables = json.loads(variables) if variables.strip() else {}
            except ValueError:
                variables = {}
        payload = {"query": gql.get("query", ""), "variables": variables}
        return Body(mode="json", content=json.dumps(payload, indent=2))
    return Body()


def _pm_request(req: dict[str, Any], inherited: Auth, warnings: list[str]) -> RequestSpec:
    method = str(req.get("method") or "GET").upper()
    if method not in METHODS:
        warnings.append(f"unsupported method {method!r} imported as GET")
        method = "GET"
    url_field = req.get("url") or ""
    if isinstance(url_field, dict):
        base, params = _split_url(str(url_field.get("raw") or ""))
        if isinstance(url_field.get("query"), list):
            params = [
                KeyValue(
                    key=str(q.get("key") or ""),
                    value=_to_str(q.get("value")),
                    enabled=not q.get("disabled", False),
                )
                for q in url_field["query"]
                if isinstance(q, dict)
            ]
        for var in url_field.get("variable") or []:
            if isinstance(var, dict) and var.get("key"):
                key = str(var["key"])
                replacement = _to_str(var.get("value")) or "{{" + key + "}}"
                base = re.sub(rf":{re.escape(key)}(?=/|$|\?)", lambda _m: replacement, base)
    else:
        base, params = _split_url(str(url_field))
    headers = [
        KeyValue(key=str(h["key"]), value=_to_str(h.get("value")), enabled=not h.get("disabled", False))
        for h in req.get("header") or []
        if isinstance(h, dict) and h.get("key")
    ]
    return RequestSpec(
        method=method,  # type: ignore[arg-type]
        url=base,
        params=params,
        headers=headers,
        body=_pm_body(req.get("body"), warnings),
        auth=_pm_auth(req["auth"]) if req.get("auth") else inherited,
        description=_pm_description(req.get("description")),
        assertions=_status_ok(),
    )


def _has_test_script(events: Any) -> bool:
    return isinstance(events, list) and any(isinstance(e, dict) and e.get("listen") == "test" for e in events)


def import_postman(doc: dict[str, Any]) -> ImportedCollection:
    info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
    col = ImportedCollection(
        format="postman",
        name=_clip(str(info.get("name") or "Imported collection")),
        description=_pm_description(info.get("description")),
    )
    for var in doc.get("variable") or []:
        if isinstance(var, dict) and var.get("key"):
            col.variables.append(
                Variable(key=str(var["key"]), value=_to_str(var.get("value")), enabled=not var.get("disabled", False))
            )
    scripts = _has_test_script(doc.get("event"))

    def walk(items: Any, prefix: str, inherited: Auth) -> None:
        nonlocal scripts
        for entry in items or []:
            if not isinstance(entry, dict):
                continue
            scripts = scripts or _has_test_script(entry.get("event"))
            auth = _pm_auth(entry["auth"]) if entry.get("auth") else inherited
            full = f"{prefix}{entry.get('name') or 'Untitled'}"
            if "item" in entry:
                walk(entry["item"], f"{full} / ", auth)
                continue
            req = entry.get("request")
            if isinstance(req, str):
                req = {"url": req, "method": "GET"}
            if isinstance(req, dict):
                col.requests.append(ImportedRequest(name=_clip(full), spec=_pm_request(req, auth, col.warnings)))

    walk(doc.get("item"), "", _pm_auth(doc.get("auth")))
    if scripts:
        col.warnings.append("Postman test scripts (JavaScript) were not imported; recreate the checks as assertions")
    if not col.requests:
        raise ValueError("the Postman collection has no requests")
    return col


# --- native -----------------------------------------------------------------------


def import_native(doc: dict[str, Any]) -> ImportedCollection:
    try:
        data = CollectionExport.model_validate(doc)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ValueError(f"invalid collection export at {where}: {first['msg']}") from exc
    return ImportedCollection(
        format="native",
        name=data.name,
        description=data.description,
        variables=data.variables,
        requests=[
            ImportedRequest(name=r.name, spec=RequestSpec.model_validate(r.model_dump(exclude={"name"})))
            for r in data.requests
        ],
    )
