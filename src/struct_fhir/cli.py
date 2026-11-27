"""Command-line interface.

Examples
--------
    python -m struct_fhir.cli examples/sample_notes/01_pneumonia.txt -o bundle.json
    python -m struct_fhir.cli note.txt --demo examples/fixtures/01_pneumonia.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extractor import DEFAULT_MODEL, ClinicalNoteExtractor, ExtractionError, extract_from_fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="struct-fhir", description="Convert a free-text clinical note to a FHIR R4 Bundle.")
    parser.add_argument("note", type=Path, help="Path to a .txt clinical note")
    parser.add_argument("-o", "--output", type=Path, help="Write the FHIR Bundle JSON here (default: stdout)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--demo", type=Path, metavar="FIXTURE", help="Offline mode: use a saved extraction JSON instead of the API"
    )
    args = parser.parse_args(argv)
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    note = args.note.read_text(encoding="utf-8")
    try:
        if args.demo:
            result = extract_from_fixture(json.loads(args.demo.read_text(encoding="utf-8")), note)
        else:
            result = ClinicalNoteExtractor(model=args.model, max_retries=args.max_retries).extract(note)
    except ExtractionError as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(result.bundle, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {len(result.bundle['entry'])} FHIR resources to {args.output}", file=sys.stderr)
    else:
        print(payload)
    print(f"attempts={result.attempts} tokens_in={result.input_tokens} tokens_out={result.output_tokens}", file=sys.stderr)
    for w in result.warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
