# fastapi_backend/tests/unit/test_content_inspector.py
"""Unit tests for ContentInspectorService sensitivity resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List

from app.schemas.ai_request import (
    AIRequestMetadata,
    AIRequestPayload,
    AIRequestSchema,
    MessageSchema,
    SensitivityLevel,
)
from app.services.content_inspector_service import ContentInspectorService


@dataclass
class FakeEnt:
    label_: str
    text: str


class FakeDoc:
    def __init__(self, ents: List[FakeEnt]) -> None:
        self.ents = ents


class FakeNLP:
    def __init__(self, ents: List[FakeEnt]) -> None:
        self._ents = ents
        self.called = False

    def __call__(self, _text: str) -> FakeDoc:
        self.called = True
        return FakeDoc(self._ents)


class ExplodingNLP:
    def __call__(self, _text: str) -> FakeDoc:  # type: ignore[name-defined]
        raise AssertionError("spaCy nlp should not be called when sensitivity is already HIGH")


def test_clean_input_stays_low() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="Hello world")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.LOW
    assert nlp.called is True


def test_pii_upgrades_to_high() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[FakeEnt(label_="PERSON", text="John Smith")])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="Contact John Smith")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_already_high_does_not_call_nlp() -> None:
    service = ContentInspectorService()
    nlp = ExplodingNLP()

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="Anything")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.HIGH, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH


def test_email_regex_upgrades_to_high_even_without_spacy_ents() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[
                MessageSchema(
                    role="user",
                    content="Please email me at alice.smith+demo@example.co.uk about the proposal.",
                )
            ]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_phone_number_not_detected_without_spacy_phone_ent() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[
                MessageSchema(
                    role="user",
                    content="Call me at (415) 555-2671 tomorrow morning.",
                )
            ]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_ssn_like_pattern_detected_by_regex() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[
                MessageSchema(
                    role="user",
                    content="My SSN is 123-45-6789, can you update my account?",
                )
            ]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_credit_card_like_pattern_detected_by_luhn() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[
                MessageSchema(
                    role="user",
                    content="Card 4111 1111 1111 1111 exp 01/30 CVV 123",
                )
            ]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_org_entity_not_upgraded_by_default() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[FakeEnt(label_="ORG", text="Microsoft")])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="I work at Microsoft.")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.LOW
    assert nlp.called is True


def test_org_entity_upgraded_in_prod_when_intent_allowed(monkeypatch) -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[FakeEnt(label_="ORG", text="Microsoft")])
    monkeypatch.setenv("PII_ALLOW_LOW_SIGNAL_INTENTS", "general_chat")

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="I work at Microsoft.")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="prod"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_iban_detected() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    # Example IBAN (DE89370400440532013000).
    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="IBAN DE89370400440532013000")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_address_detected_by_heuristics() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="Send to 123 Main St, please.")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_jwt_secret_detected() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    # Common sample JWT (three base64url segments).
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4iLCJpYXQiOjE1MTYyMzkwMjJ9."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content=f"My JWT is: {token}")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True


def test_api_key_detected_by_pattern() -> None:
    service = ContentInspectorService()
    nlp = FakeNLP(ents=[])

    body = AIRequestSchema(
        intent="general_chat",
        payload=AIRequestPayload(
            messages=[MessageSchema(role="user", content="AWS key AKIAIOSFODNN7EXAMPLE")]
        ),
        metadata=AIRequestMetadata(sensitivity=SensitivityLevel.LOW, environment="dev"),
    )

    resolved = asyncio.run(service.resolve_sensitivity(body, nlp))
    assert resolved == SensitivityLevel.HIGH
    assert nlp.called is True

