import copy

import pytest
from pydantic import ValidationError

from struct_fhir.schemas import ClinicalExtraction, find_ungrounded_items


def test_fixture_is_valid(pneumonia_fixture):
    ex = ClinicalExtraction.model_validate(pneumonia_fixture)
    assert ex.patient.gender.value == "male"
    assert len(ex.medications) == 3


def test_rejects_invalid_gender(pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["patient"]["gender"] = "M"
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(bad)


def test_rejects_unknown_fields(pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["patient"]["ssn"] = "123"
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(bad)


@pytest.mark.parametrize("code", ["J18", "XYZ", "J18.99999", "U07.1"])
def test_rejects_malformed_icd10(pneumonia_fixture, code):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["diagnoses"][0]["icd10_code"] = code
    if code == "J18":  # 3-character category codes are valid ICD-10-CM
        ClinicalExtraction.model_validate(bad)
        return
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(bad)


def test_icd10_is_uppercased(pneumonia_fixture):
    data = copy.deepcopy(pneumonia_fixture)
    data["diagnoses"][0]["icd10_code"] = "j18.9"
    assert ClinicalExtraction.model_validate(data).diagnoses[0].icd10_code == "J18.9"


def test_rejects_missing_evidence(pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["symptoms"][0]["evidence"] = ""
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(bad)


def test_rejects_non_numeric_rxnorm(pneumonia_fixture):
    bad = copy.deepcopy(pneumonia_fixture)
    bad["medications"][0]["rxnorm_code"] = "AMOX"
    with pytest.raises(ValidationError):
        ClinicalExtraction.model_validate(bad)


def test_all_sample_fixtures_are_grounded(all_samples):
    for name, note, fixture in all_samples:
        ex = ClinicalExtraction.model_validate(fixture)
        assert find_ungrounded_items(ex, note) == [], name


def test_grounding_detects_hallucination(pneumonia_note, pneumonia_fixture):
    data = copy.deepcopy(pneumonia_fixture)
    data["medications"].append({"name": "warfarin", "dose": "5 mg", "evidence": "warfarin 5 mg daily"})
    warnings = find_ungrounded_items(ClinicalExtraction.model_validate(data), pneumonia_note)
    assert len(warnings) == 1 and "warfarin" in warnings[0]
