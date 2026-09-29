from __future__ import annotations

from pathlib import Path

import pytest

from lt.config import parse_config_text
from lt.jmx import JmxError, convert_jmx, jmx_to_yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def shop_jmx() -> str:
    return (FIXTURES / "shop.jmx").read_text(encoding="utf-8")


def test_convert_shop_plan() -> None:
    cfg, warnings = convert_jmx(shop_jmx(), data_dir=FIXTURES)
    assert cfg["name"] == "Shop checkout"
    assert cfg["base_url"] == "http://127.0.0.1:8080"  # ${host} resolved from variables
    assert cfg["safety"]["allowlist"] == ["127.0.0.1"]
    # Scheduler duration 60s includes the 10s ramp-up; loops = -1 means no iteration cap.
    assert cfg["model"] == {"type": "closed", "users": 25, "ramp_up": "10s", "duration": "50s"}
    login, search = cfg["routes"]
    assert login["name"] == "Checkout / Login" and login["method"] == "POST"
    assert login["body"] == '{"username":"{{username}}","password":"{{password}}"}'
    assert login["headers"] == {"Accept": "application/json", "Content-Type": "application/json"}
    assert login["expect_status"] == [200] and login["extract"] == {"token": "$.token"}
    assert login["think_time"] == "500ms-1500ms"
    assert search["path"] == "/app/products?q=desk%20lamp&page={{$randomInt}}"
    assert search["headers"]["Authorization"] == "Bearer {{token}}"
    assert search["assertions"] == {"max_ms": 800.0, "jsonpath": {"$.items[0].id": "*"}}
    assert cfg["variables"] == {"host": "127.0.0.1", "password": "demo"}
    assert cfg["data"]["columns"] == ["username"] and cfg["data"]["csv"] == "alice\nbob\ncarol"
    assert any("__Random" in w for w in warnings)


def test_yaml_output_is_a_valid_runnable_config() -> None:
    text, _ = jmx_to_yaml(shop_jmx(), data_dir=FIXTURES)
    cfg = parse_config_text(text)
    assert cfg.model.is_closed and cfg.model.peak_users == 25 and cfg.model.total_duration == 60
    assert cfg.data is not None and [r["username"] for r in cfg.data.records()] == [
        "alice", "bob", "carol",
    ]  # fmt: skip


def test_missing_csv_file_gets_a_placeholder() -> None:
    cfg, warnings = convert_jmx(shop_jmx())
    assert cfg["data"]["rows"] == [{"username": ""}]
    assert any("paste the file" in w for w in warnings)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("not xml", "not a valid"),
        ("<root/>", "not a JMeter test plan"),
        ("<jmeterTestPlan><hashTree/></jmeterTestPlan>", "no TestPlan"),
        (
            '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
            "<jmeterTestPlan><hashTree>&b;</hashTree></jmeterTestPlan>",
            "not a valid",
        ),
    ],
)
def test_rejects_invalid_or_unsafe_input(text: str, fragment: str) -> None:
    with pytest.raises(JmxError, match=fragment):
        convert_jmx(text)


def test_thread_group_without_samplers() -> None:
    text = shop_jmx().replace('testname="Login" enabled="true"', 'testname="Login" enabled="false"')
    text = text.replace('testname="Search" enabled="true"', 'testname="Search" enabled="false"')
    with pytest.raises(JmxError, match="no HTTP Request"):
        convert_jmx(text)
