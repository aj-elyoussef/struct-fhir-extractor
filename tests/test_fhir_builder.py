import json

from struct_fhir.fhir_builder import build_bundle
from struct_fhir.fhir_models import Bundle
from struct_fhir.schemas import ClinicalExtraction

TS = "2026-11-27T00:00:00+00:00"


def _bundle(fixture, note):
    return build_bundle(ClinicalExtraction.model_validate(fixture), note, timestamp=TS)


def test_bundle_shape(pneumonia_fixture, pneumonia_note):
    b = _bundle(pneumonia_fixture, pneumonia_note)
    assert b["resourceType"] == "Bundle" and b["type"] == "transaction"
    types = [e["resource"]["resourceType"] for e in b["entry"]]
    assert types.count("Patient") == 1
    assert types.count("Observation") == 4
    assert types.count("Condition") == 2
    assert types.count("MedicationRequest") == 3


def test_bundle_round_trips_through_strict_model(all_samples):
    for _, note, fixture in all_samples:
        b = _bundle(fixture, note)
        Bundle.model_validate(b)  # raises if any element is malformed
        json.dumps(b)  # serialisable


def test_all_references_resolve(all_samples):
    for _, note, fixture in all_samples:
        b = _bundle(fixture, note)
        full_urls = {e["fullUrl"] for e in b["entry"]}
        for e in b["entry"]:
            subj = e["resource"].get("subject")
            if subj:
                assert subj["reference"] in full_urls


def test_deterministic_output(pneumonia_fixture, pneumonia_note):
    assert _bundle(pneumonia_fixture, pneumonia_note) == _bundle(pneumonia_fixture, pneumonia_note)


def test_codes_and_statuses(pneumonia_fixture, pneumonia_note):
    b = _bundle(pneumonia_fixture, pneumonia_note)
    conds = [e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Condition"]
    assert conds[0]["code"]["coding"][0] == {
        "system": "http://hl7.org/fhir/sid/icd-10-cm",
        "code": "J18.9",
        "display": "Community-acquired pneumonia, right lower lobe",
    }
    meds = [e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "MedicationRequest"]
    assert meds[1]["intent"] == "plan"  # metformin is continued, not newly ordered
    assert meds[0]["dosageInstruction"][0]["route"]["coding"][0]["code"] == "26643006"
    obs = [e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "Observation"]
    assert obs[-1]["code"]["text"] == "chest pain" and obs[-1]["valueBoolean"] is False


def test_refuted_condition_has_no_clinical_status(all_samples):
    _, note, fixture = [s for s in all_samples if s[0] == "03_cellulitis"][0]
    b = _bundle(fixture, note)
    dvt = next(e["resource"] for e in b["entry"] if e["resource"].get("code", {}).get("text") == "Deep vein thrombosis")
    assert "clinicalStatus" not in dvt
    assert dvt["verificationStatus"]["coding"][0]["code"] == "refuted"
