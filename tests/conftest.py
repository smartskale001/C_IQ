"""Shared pytest fixtures for the ContractIQ API test suite."""

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

ROOT = Path(__file__).resolve().parents[1]

# Ensure the project root is importable even when pytest changes sys.path.
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import services.contract_extractor as ce  # noqa: E402
import main  # noqa: E402
from main import app, TEMP_UPLOAD_DIR  # noqa: E402
from db import get_session  # noqa: E402

# Always import the table models so SQLModel metadata knows about them.
import models.contract_extract  # noqa: E402, F401
import models.risk  # noqa: E402, F401
import models.audit  # noqa: E402, F401


# ---- Test database: in-memory engine overridden into the app ----
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(test_engine)


def _override_get_session():
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def temp_doc_dir():
    """A throwaway subdirectory under the app's temp folder."""
    folder = TEMP_UPLOAD_DIR / f"pytest_{uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=True)
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


class FakeOpenAIResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeOpenAIClient:
    """Stands in for services.contract_extractor.requests.post."""

    def __init__(self, *_args, **_kwargs):
        pass

    def __call__(self, *_args, **_kwargs):
        content = json.dumps({
            "subject_to_lease": "Yes - tenanted",
            "date_of_tenancy": "2026-11-14",
            "contract_price": 1285000,
            "deposit_amount": 128500,
            "deposit_due_date": "2026-09-13",
            "subject_to_finance": True,
            "settlement_date": "30 days from signing",
            "gst_clause": "Price is GST inclusive",
            "terms_contract": "Standard terms apply",
            "default_provisions": "Interest 12% p.a. on default",
            "due_date_extension": None,
            "special_conditions": None,
            "extracted_parameters": [
                {
                    "parameter_name": "contract_price",
                    "parameter_value": 1285000,
                    "confidence_score": 98,
                    "reference": {
                        "page_num": 2,
                        "section_number": "3.2",
                        "section_title": "Purchase Price",
                    },
                }
            ],
        })
        return FakeOpenAIResponse({"choices": [{"message": {"content": content}}]})


@pytest.fixture()
def mock_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ce.requests, "post", FakeOpenAIClient())
    ce._extractor = None
    yield
    ce._extractor = None