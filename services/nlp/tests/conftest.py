import json
import os
import sys
from pathlib import Path

import pytest

# Tests use the small "hash" embedder: no model download, fast, deterministic.
os.environ.setdefault("EMBEDDING_BACKEND", "hash")

ROOT = Path(__file__).resolve().parent.parent  # services/nlp/
sys.path.insert(0, str(ROOT / "app"))

CONTRACTS = ROOT.parents[1] / "docs" / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


@pytest.fixture(scope="session")
def contract():
    """Validators for the JSON contract files, so tests fail if the service drifts from the contract."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource

    out_schema = json.loads((CONTRACTS / "nlp_output_schema.json").read_text())
    api_schema = json.loads((CONTRACTS / "nlp_service_api.json").read_text())
    registry = Registry().with_resources(
        [(s["$id"], Resource.from_contents(s)) for s in (out_schema, api_schema)]
    )

    def validator_for(name: str) -> Draft7Validator:
        if name == "analyze_response":
            return Draft7Validator(out_schema, registry=registry)
        sub = {"$ref": f"{api_schema['$id']}#/definitions/{name}"}
        return Draft7Validator(sub, registry=registry)

    return validator_for


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
