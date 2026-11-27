"""Extractor tests using a fake Anthropic client (no network, no API key)."""

import copy
from types import SimpleNamespace

import pytest

from struct_fhir.extractor import TOOL_NAME, ClinicalNoteExtractor, ExtractionError, build_tool_definition


def _response(payload, tool_id="toolu_1"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id=tool_id, name=TOOL_NAME, input=payload)],
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


class FakeClient:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return _response(self._payloads.pop(0), tool_id=f"toolu_{len(self.calls)}")


def test_tool_schema_is_self_contained():
    tool = build_tool_definition()
    text = str(tool["input_schema"])
    assert "$ref" not in text and "$defs" not in text
    assert set(tool["input_schema"]["required"]) == {"patient"}


def test_happy_path(pneumonia_note, pneumonia_fixture):
    client = FakeClient([pneumonia_fixture])
    result = ClinicalNoteExtractor(client=client).extract(pneumonia_note)
    assert result.attempts == 1
    assert result.warnings == []
    assert len(result.bundle["entry"]) == 10
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert call["temperature"] == 0
    assert "<clinical_note>" in call["messages"][0]["content"]


def test_self_repair_after_schema_error(pneumonia_note, pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["patient"]["gender"] = "Male (M)"
    client = FakeClient([bad, pneumonia_fixture])
    result = ClinicalNoteExtractor(client=client).extract(pneumonia_note)
    assert result.attempts == 2
    assert "patient.gender" in result.repair_log[0]
    tool_result = client.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["is_error"] is True
    assert tool_result["tool_use_id"] == "toolu_1"
    assert result.input_tokens == 200


def test_self_repair_after_hallucinated_evidence(pneumonia_note, pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["diagnoses"][0]["evidence"] = "confirmed sepsis"
    client = FakeClient([bad, pneumonia_fixture])
    result = ClinicalNoteExtractor(client=client).extract(pneumonia_note)
    assert result.attempts == 2
    assert "Grounding check failed" in result.repair_log[0]


def test_gives_up_after_retry_budget(pneumonia_note, pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["patient"]["age_years"] = -4
    client = FakeClient([bad, bad, bad])
    with pytest.raises(ExtractionError):
        ClinicalNoteExtractor(client=client, max_retries=2).extract(pneumonia_note)
    assert len(client.calls) == 3


def test_empty_note_rejected():
    with pytest.raises(ValueError):
        ClinicalNoteExtractor(client=FakeClient([])).extract("   ")
