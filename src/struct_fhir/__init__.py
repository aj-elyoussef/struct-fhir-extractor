"""Struct: unstructured clinical note to HL7 FHIR R4 JSON extractor."""

from .extractor import ClinicalNoteExtractor, ExtractionError, ExtractionResult, extract_from_fixture
from .fhir_builder import build_bundle
from .schemas import ClinicalExtraction, find_ungrounded_items

__all__ = [
    "ClinicalNoteExtractor",
    "ExtractionError",
    "ExtractionResult",
    "ClinicalExtraction",
    "build_bundle",
    "extract_from_fixture",
    "find_ungrounded_items",
]

__version__ = "1.0.0"
