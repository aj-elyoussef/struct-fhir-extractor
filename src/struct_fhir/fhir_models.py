"""Minimal, strict Pydantic models for the HL7 FHIR R4 resources Struct emits.

Only the elements Struct populates are modelled. ``extra="forbid"`` means a
typo in a field name fails loudly instead of producing silently invalid FHIR.
For full conformance testing, run the output through the official HL7 FHIR
Validator (see docs/architecture.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FhirModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def to_fhir(self) -> dict:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# ---- Data types ----------------------------------------------------------- #
class Coding(FhirModel):
    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(FhirModel):
    coding: list[Coding] | None = None
    text: str | None = None


class Reference(FhirModel):
    reference: str


class HumanName(FhirModel):
    use: Literal["official", "usual"] = "official"
    text: str
    family: str | None = None
    given: list[str] | None = None


class Identifier(FhirModel):
    system: str | None = None
    value: str


class Extension(FhirModel):
    url: str
    valueInteger: int | None = None
    valueString: str | None = None


class Annotation(FhirModel):
    text: str


class Dosage(FhirModel):
    text: str
    route: CodeableConcept | None = None


# ---- Resources ------------------------------------------------------------ #
class Patient(FhirModel):
    resourceType: Literal["Patient"] = "Patient"
    id: str
    identifier: list[Identifier] | None = None
    name: list[HumanName] | None = None
    gender: Literal["male", "female", "other", "unknown"] = "unknown"
    birthDate: str | None = None
    extension: list[Extension] | None = None


class Condition(FhirModel):
    resourceType: Literal["Condition"] = "Condition"
    id: str
    clinicalStatus: CodeableConcept | None = None  # omitted for refuted diagnoses
    verificationStatus: CodeableConcept
    category: list[CodeableConcept]
    code: CodeableConcept
    subject: Reference
    note: list[Annotation] | None = None


class Observation(FhirModel):
    resourceType: Literal["Observation"] = "Observation"
    id: str
    status: Literal["preliminary", "final", "amended"] = "preliminary"
    code: CodeableConcept
    subject: Reference
    valueBoolean: bool | None = None
    note: list[Annotation] | None = None


class MedicationRequest(FhirModel):
    resourceType: Literal["MedicationRequest"] = "MedicationRequest"
    id: str
    status: Literal["active", "completed", "draft", "unknown"] = "active"
    intent: Literal["order", "plan", "proposal"] = "order"
    medicationCodeableConcept: CodeableConcept
    subject: Reference
    dosageInstruction: list[Dosage] | None = None
    note: list[Annotation] | None = None


Resource = Patient | Condition | Observation | MedicationRequest


class BundleRequest(FhirModel):
    method: Literal["POST", "PUT"] = "POST"
    url: str


class BundleEntry(FhirModel):
    fullUrl: str
    resource: Resource = Field(..., discriminator="resourceType")
    request: BundleRequest


class Bundle(FhirModel):
    resourceType: Literal["Bundle"] = "Bundle"
    type: Literal["transaction", "collection"] = "transaction"
    timestamp: str
    entry: list[BundleEntry]
