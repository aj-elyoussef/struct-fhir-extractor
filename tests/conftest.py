import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EXAMPLES = ROOT / "examples"


@pytest.fixture
def pneumonia_note() -> str:
    return (EXAMPLES / "sample_notes" / "01_pneumonia.txt").read_text(encoding="utf-8")


@pytest.fixture
def pneumonia_fixture() -> dict:
    return json.loads((EXAMPLES / "fixtures" / "01_pneumonia.json").read_text(encoding="utf-8"))


@pytest.fixture
def all_samples():
    pairs = []
    for note_path in sorted((EXAMPLES / "sample_notes").glob("*.txt")):
        fixture = json.loads((EXAMPLES / "fixtures" / f"{note_path.stem}.json").read_text(encoding="utf-8"))
        pairs.append((note_path.stem, note_path.read_text(encoding="utf-8"), fixture))
    return pairs
