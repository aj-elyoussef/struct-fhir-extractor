"""Deterministic mapping from a validated ``ClinicalExtraction`` to a FHIR R4 Bundle.

No LLM is involved here: identical input always yields identical output.
Resource IDs are UUIDv5 values derived from the note's SHA-256 hash, so
re-running the same note produces the same IDs (idempotent uploads).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from .fhir_models import (
    Annotation,
    Bundle,
    BundleEntry,
    BundleRequest,
    CodeableConcept,
    Coding,
    Condition,
    Dosage,
    Extension,
    HumanName,
    Identifier,
    MedicationRequest,
    Observation,
    Patient,
    Reference,
)
from .schemas import ClinicalExtraction, DiagnosisStatus, Route

ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
RXNORM_SYSTEM = "http://www.nlm.nih.gov/research/umls/rxnorm"
SNOMED_SYSTEM = "http://snomed.info/sct"
CLINICAL_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"
VER_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-category"
STATED_AGE_EXT = "https://github.com/struct-fhir/StructureDefinition/stated-age"
MRN_SYSTEM = "urn:struct:mrn"

ROUTE_SNOMED: dict[Route, tuple[str, str]] = {
    Route.oral: ("26643006", "Oral route"),
    Route.intravenous: ("47625008", "Intravenous route"),
    Route.intramuscular: ("78421000", "Intramuscular route"),
    Route.subcutaneous: ("34206005", "Subcutaneous route"),
    Route.topical: ("6064005", "Topical route"),
    Route.inhaled: ("447694001", "Respiratory tract route"),
    Route.sublingual: ("37839007", "Sublingual route"),
    Route.rectal: ("37161004", "Rectal route"),
}


def _id_factory(note: str):
    namespace = uuid.UUID(hashlib.sha256(note.encode("utf-8")).hexdigest()[:32])
    counter = {"n": 0}

    def next_id(kind: str) -> str:
        counter["n"] += 1
        return str(uuid.uuid5(namespace, f"{kind}-{counter['n']}"))

    return next_id


def _split_name(full: str) -> tuple[str | None, list[str] | None]:
    parts = full.split()
    if len(parts) < 2:
        return None, None
    return parts[-1], parts[:-1]


def _evidence_note(evidence: str) -> list[Annotation]:
    return [Annotation(text=f'Source: "{evidence}"')]


def build_bundle(extraction: ClinicalExtraction, note: str, timestamp: str | None = None) -> dict:
    """Convert a validated extraction into a FHIR R4 *transaction* Bundle (as a dict)."""
    next_id = _id_factory(note)
    entries: list[BundleEntry] = []

    # ---- Patient ---------------------------------------------------------- #
    p = extraction.patient
    patient_id = next_id("patient")
    patient_ref = Reference(reference=f"urn:uuid:{patient_id}")
    name = None
    if p.full_name:
        family, given = _split_name(p.full_name)
        name = [HumanName(text=p.full_name, family=family, given=given)]
    patient = Patient(
        id=patient_id,
        identifier=[Identifier(system=MRN_SYSTEM, value=p.mrn)] if p.mrn else None,
        name=name,
        gender=p.gender.value,
        birthDate=p.birth_date.isoformat() if p.birth_date else None,
        extension=[Extension(url=STATED_AGE_EXT, valueInteger=p.age_years)] if p.age_years is not None else None,
    )
    entries.append(_entry(patient_id, patient, "Patient"))

    # ---- Symptoms -> Observation ----------------------------------------- #
    for s in extraction.symptoms:
        rid = next_id("observation")
        details = ", ".join(
            x for x in (f"onset: {s.onset}" if s.onset else "", f"severity: {s.severity}" if s.severity else "") if x
        )
        notes = _evidence_note(s.evidence) + ([Annotation(text=details)] if details else [])
        obs = Observation(
            id=rid,
            code=CodeableConcept(text=s.name),
            subject=patient_ref,
            valueBoolean=s.present,
            note=notes,
        )
        entries.append(_entry(rid, obs, "Observation"))

    # ---- Diagnoses -> Condition ------------------------------------------ #
    for d in extraction.diagnoses:
        rid = next_id("condition")
        coding = [Coding(system=ICD10_SYSTEM, code=d.icd10_code, display=d.name)] if d.icd10_code else None
        cond = Condition(
            id=rid,
            clinicalStatus=None
            if d.status == DiagnosisStatus.refuted
            else CodeableConcept(coding=[Coding(system=CLINICAL_STATUS_SYSTEM, code="active")]),
            verificationStatus=CodeableConcept(coding=[Coding(system=VER_STATUS_SYSTEM, code=d.status.value)]),
            category=[CodeableConcept(coding=[Coding(system=CATEGORY_SYSTEM, code="encounter-diagnosis")])],
            code=CodeableConcept(coding=coding, text=d.name),
            subject=patient_ref,
            note=_evidence_note(d.evidence),
        )
        entries.append(_entry(rid, cond, "Condition"))

    # ---- Medications -> MedicationRequest -------------------------------- #
    for m in extraction.medications:
        rid = next_id("medicationrequest")
        coding = [Coding(system=RXNORM_SYSTEM, code=m.rxnorm_code, display=m.name)] if m.rxnorm_code else None
        dosage_text = " ".join(x for x in (m.dose, m.frequency, f"for {m.duration}" if m.duration else None) if x)
        route = None
        if m.route and m.route in ROUTE_SNOMED:
            code, display = ROUTE_SNOMED[m.route]
            route = CodeableConcept(coding=[Coding(system=SNOMED_SYSTEM, code=code, display=display)], text=m.route.value)
        elif m.route:
            route = CodeableConcept(text=m.route.value)
        med = MedicationRequest(
            id=rid,
            status="active",
            intent="order" if m.newly_prescribed else "plan",
            medicationCodeableConcept=CodeableConcept(coding=coding, text=m.name),
            subject=patient_ref,
            dosageInstruction=[Dosage(text=dosage_text or m.name, route=route)],
            note=_evidence_note(m.evidence),
        )
        entries.append(_entry(rid, med, "MedicationRequest"))

    ts = timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return Bundle(timestamp=ts, entry=entries).to_fhir()


def _entry(rid: str, resource, resource_type: str) -> BundleEntry:
    return BundleEntry(
        fullUrl=f"urn:uuid:{rid}",
        resource=resource,
        request=BundleRequest(method="POST", url=resource_type),
    )
