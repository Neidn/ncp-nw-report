from __future__ import annotations

import json
from importlib import resources
from typing import Any

import pytest


@pytest.fixture
def demo_raw() -> dict[str, Any]:
    text = (
        resources.files("ncp_nw_report")
        .joinpath("demo/demo_raw.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)
