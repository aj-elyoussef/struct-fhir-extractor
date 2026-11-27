# Architecture and design decisions

## Two-stage design: probabilistic extraction, deterministic mapping

Struct deliberately separates the work into two stages.

| Stage | Who does it | Output | Guarantees |
|---|---|---|---|
| 1. Extraction | Claude (forced tool use) | `ClinicalExtraction` (Pydantic) | Schema-valid, every fact grounded in a verbatim quote |
| 2. Mapping | Plain Python (`fhir_builder.py`) | FHIR R4 `Bundle` | Deterministic, idempotent, strictly typed |

Asking an LLM to write raw FHIR directly tends to produce plausible but subtly invalid resources (wrong code systems,
misplaced elements, broken references). A small, flat, clinician-readable intermediate schema is much easier for the
model to fill correctly, and all FHIR-specific structure is then applied by code that can be unit tested.

## Mapping rules

| Extraction field | FHIR element |
|---|---|
| `patient.gender` | `Patient.gender` (AdministrativeGender) |
| `patient.age_years` | `Patient.extension` (custom `stated-age` extension; FHIR Patient has no age element) |
| `patient.mrn` | `Patient.identifier` |
| `symptom.present` | `Observation.valueBoolean` (false = explicitly denied) |
| `symptom.onset/severity` | `Observation.note` |
| `diagnosis.status` | `Condition.verificationStatus` (`clinicalStatus` omitted when `refuted`) |
| `diagnosis.icd10_code` | `Condition.code.coding` (`http://hl7.org/fhir/sid/icd-10-cm`) |
| `medication.route` | `MedicationRequest.dosageInstruction.route` (SNOMED CT route codes) |
| `medication.newly_prescribed` | `MedicationRequest.intent` = `order` (new) or `plan` (continued) |
| `*.evidence` | `note` annotation on each resource, for audit and provenance |

## Self-repair protocol

```
user:       note
assistant:  tool_use(record_clinical_extraction, input=…)
            → Pydantic / grounding check fails
user:       tool_result(is_error=true, content="- patient.gender: Input should be 'male', 'female', …")
assistant:  tool_use(record_clinical_extraction, input=corrected)
            → passes → mapped to FHIR
```

The loop is bounded by `max_retries`. If the budget runs out, `ExtractionError` is raised with the full repair log
rather than returning unvalidated data.

## Known limitations

* Codes (ICD-10-CM, RxNorm) are model-suggested and only format-validated. Production use would verify them against a
  terminology server.
* The FHIR Pydantic models cover only the elements Struct emits. For formal conformance, run the output through the
  [official HL7 FHIR Validator](https://confluence.hl7.org/display/FHIR/Using+the+FHIR+Validator).
* Sending real patient data to any external API requires appropriate privacy agreements and de-identification.
