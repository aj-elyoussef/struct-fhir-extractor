"""Strict Pydantic schemas for the *intermediate* clinical extraction.

Claude is forced to return data in exactly this shape (via tool use). The
schema is deliberately narrow: enums instead of free text where possible,
regex-validated codes, and a verbatim ``evidence`` quote on every clinical
item so each fact can be traced back to the source note.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ICD-10-CM: letter, digit, digit/A/B, optional dot + 1-4 alphanumerics (U excluded at start).
ICD10_PATTERN = r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$"
# RxNorm concept IDs are purely numeric.
RXNORM_PATTERN = r"^[0-9]{1,8}$"


class StrictModel(BaseModel):
    """Base model: reject unknown keys and trim whitespace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Gender(str, Enum):
    """Mirrors the FHIR R4 AdministrativeGender value set."""

    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class DiagnosisStatus(str, Enum):
    """Subset of FHIR condition-ver-status."""

    confirmed = "confirmed"
    provisional = "provisional"
    differential = "differential"
    refuted = "refuted"


class Route(str, Enum):
    oral = "oral"
    intravenous = "intravenous"
    intramuscular = "intramuscular"
    subcutaneous = "subcutaneous"
    topical = "topical"
    inhaled = "inhaled"
    sublingual = "sublingual"
    rectal = "rectal"
    other = "other"


class PatientDemographics(StrictModel):
    full_name: str | None = Field(None, description="Patient name exactly as written, if present.")
    gender: Gender = Field(Gender.unknown, description="Administrative gender. Use 'unknown' if not stated.")
    age_years: int | None = Field(None, ge=0, le=130, description="Age in whole years, if stated.")
    birth_date: date | None = Field(None, description="ISO date of birth (YYYY-MM-DD), only if explicitly stated.")
    mrn: str | None = Field(None, description="Medical record number, if present.")


class Symptom(StrictModel):
    name: str = Field(..., min_length=1, description="Symptom in plain clinical terms, e.g. 'productive cough'.")
    present: bool = Field(True, description="False if the note explicitly denies it (e.g. 'denies chest pain').")
    onset: str | None = Field(None, description="Onset or duration as written, e.g. '3 days'.")
    severity: str | None = Field(None, description="Severity as written, e.g. 'mild', '7/10'.")
    evidence: str = Field(..., min_length=1, description="Verbatim quote from the note supporting this item.")


class Diagnosis(StrictModel):
    name: str = Field(..., min_length=1, description="Diagnosis or assessment, e.g. 'community-acquired pneumonia'.")
    status: DiagnosisStatus = Field(DiagnosisStatus.confirmed)
    icd10_code: str | None = Field(
        None,
        pattern=ICD10_PATTERN,
        description="ICD-10-CM code ONLY if you are highly confident; otherwise null.",
    )
    evidence: str = Field(..., min_length=1, description="Verbatim quote from the note supporting this item.")

    @field_validator("icd10_code", mode="before")
    @classmethod
    def _upper_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if isinstance(v, str) and v.strip() else None


class Medication(StrictModel):
    name: str = Field(..., min_length=1, description="Drug name, generic preferred, e.g. 'amoxicillin'.")
    dose: str | None = Field(None, description="Dose with unit, e.g. '500 mg'.")
    route: Route | None = None
    frequency: str | None = Field(None, description="Frequency as written, e.g. 'TID', 'every 8 hours'.")
    duration: str | None = Field(None, description="Duration as written, e.g. '7 days'.")
    rxnorm_code: str | None = Field(
        None, pattern=RXNORM_PATTERN, description="RxNorm CUI ONLY if highly confident; otherwise null."
    )
    newly_prescribed: bool = Field(True, description="True if prescribed/started in this visit; False if an existing med.")
    evidence: str = Field(..., min_length=1, description="Verbatim quote from the note supporting this item.")


class ClinicalExtraction(StrictModel):
    """Top-level object Claude must return via the ``record_clinical_extraction`` tool."""

    patient: PatientDemographics
    symptoms: list[Symptom] = Field(default_factory=list)
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Grounding check: every evidence quote must actually appear in the note.
# --------------------------------------------------------------------------- #
def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def find_ungrounded_items(extraction: ClinicalExtraction, note: str) -> list[str]:
    """Return human-readable warnings for evidence quotes not found in the note.

    This is a deterministic guard against hallucination: the model may
    paraphrase a fact, but it cannot invent one without failing this check.
    """
    haystack = _normalise(note)
    warnings: list[str] = []
    groups = (("symptom", extraction.symptoms), ("diagnosis", extraction.diagnoses), ("medication", extraction.medications))
    for label, items in groups:
        for item in items:
            if _normalise(item.evidence) not in haystack:
                warnings.append(f"{label} '{item.name}': evidence not found verbatim in note -> \"{item.evidence}\"")
    return warnings
