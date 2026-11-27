"""Struct - Streamlit side-by-side comparison UI.

Run:  streamlit run app.py
"""

from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass
sys.path.insert(0, str(ROOT / "src"))

from struct_fhir import ClinicalNoteExtractor, ExtractionError, extract_from_fixture  # noqa: E402
from struct_fhir.extractor import DEFAULT_MODEL  # noqa: E402

NOTES_DIR = ROOT / "examples" / "sample_notes"
FIXTURES_DIR = ROOT / "examples" / "fixtures"

st.set_page_config(page_title="Struct | Clinical Note to FHIR", page_icon="🩺", layout="wide")


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("🩺 Struct")
    st.caption("Unstructured clinical notes → HL7 FHIR R4 JSON")

    samples = {p.stem: p for p in sorted(NOTES_DIR.glob("*.txt"))}
    choice = st.selectbox("Load a synthetic sample note", ["(none)"] + list(samples))

    env_key = os.getenv("ANTHROPIC_API_KEY", "")
    api_key = st.text_input(
        "Anthropic API key", value="", type="password", help="Leave blank to use ANTHROPIC_API_KEY from your environment."
    )
    has_key = bool(api_key or env_key)
    demo = st.toggle("Demo mode (no API call)", value=not has_key, help="Uses saved extractions for the sample notes.")
    model = st.text_input("Model", value=DEFAULT_MODEL, disabled=demo)
    max_retries = st.slider("Self-repair retries", 0, 4, 2, disabled=demo)

    st.divider()
    st.markdown(
        "**Pipeline**\n1. Claude forced tool call\n2. Pydantic validation\n3. Evidence grounding check\n"
        "4. Self-repair on errors\n5. Deterministic FHIR mapping"
    )
    st.caption("⚠️ Portfolio demo only. Use synthetic or de-identified notes. Not for clinical use.")

default_note = samples[choice].read_text(encoding="utf-8") if choice != "(none)" else ""

# --------------------------------------------------------------------------- #
# Main layout: note on the left, structured output on the right
# --------------------------------------------------------------------------- #
left, right = st.columns(2, gap="large")

with left:
    st.subheader("📝 Free-text physician note")
    note = st.text_area("Note", value=default_note, height=420, label_visibility="collapsed", key=f"note-{choice}")
    run = st.button("Extract to FHIR", type="primary", use_container_width=True, disabled=not note.strip())

if run:
    with st.spinner("Extracting and validating..."):
        try:
            if demo:
                fixture_path = FIXTURES_DIR / f"{choice}.json"
                if choice == "(none)" or not fixture_path.exists():
                    st.error("Demo mode only works with the bundled sample notes. Add an API key to process your own note.")
                    st.stop()
                result = extract_from_fixture(json.loads(fixture_path.read_text(encoding="utf-8")), note)
            else:
                client = None
                if api_key:
                    import anthropic

                    client = anthropic.Anthropic(api_key=api_key)
                result = ClinicalNoteExtractor(client=client, model=model, max_retries=max_retries).extract(note)
            st.session_state["result"] = result
            st.session_state["note"] = note
        except ExtractionError as exc:
            st.error(f"Extraction failed validation after retries:\n\n{exc}")
        except Exception as exc:  # surface API/auth errors in the UI
            st.error(f"{type(exc).__name__}: {exc}")


def highlight(note_text: str, quotes: list[str]) -> str:
    """Wrap each evidence quote in <mark> so reviewers can see what was used."""
    out = html.escape(note_text)
    for q in sorted({html.escape(q) for q in quotes}, key=len, reverse=True):
        out = out.replace(q, f"<mark>{q}</mark>")
    return f"<div style='white-space:pre-wrap;font-family:monospace;font-size:0.85rem'>{out}</div>"


with right:
    st.subheader("🧬 Structured FHIR output")
    result = st.session_state.get("result")
    if result is None:
        st.info("Load a sample (or paste a note) and click **Extract to FHIR**.")
    else:
        ex = result.extraction
        resource_counts = pd.Series([e["resource"]["resourceType"] for e in result.bundle["entry"]]).value_counts()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Resources", len(result.bundle["entry"]))
        c2.metric("Attempts", result.attempts)
        c3.metric("Grounding warnings", len(result.warnings))
        c4.metric("Tokens", result.input_tokens + result.output_tokens)

        tab_json, tab_entities, tab_evidence, tab_report = st.tabs(["FHIR Bundle", "Entities", "Evidence", "Validation"])
        with tab_json:
            st.json(result.bundle, expanded=2)
            st.download_button(
                "⬇️ Download Bundle JSON",
                data=json.dumps(result.bundle, indent=2),
                file_name="fhir_bundle.json",
                mime="application/fhir+json",
                use_container_width=True,
            )
        with tab_entities:
            st.markdown("**Patient**")
            st.dataframe(pd.DataFrame([ex.patient.model_dump(mode="json")]), hide_index=True, use_container_width=True)
            for label, items in (
                ("Symptoms → Observation", ex.symptoms),
                ("Diagnoses → Condition", ex.diagnoses),
                ("Medications → MedicationRequest", ex.medications),
            ):
                st.markdown(f"**{label}**")
                if items:
                    st.dataframe(
                        pd.DataFrame([i.model_dump(mode="json") for i in items]), hide_index=True, use_container_width=True
                    )
                else:
                    st.caption("None found.")
        with tab_evidence:
            quotes = [i.evidence for group in (ex.symptoms, ex.diagnoses, ex.medications) for i in group]
            st.markdown(highlight(st.session_state["note"], quotes), unsafe_allow_html=True)
        with tab_report:
            st.write(f"Model: `{result.model}`")
            st.write(resource_counts.rename("count"))
            if result.repair_log:
                st.warning("Self-repair was triggered:")
                for line in result.repair_log:
                    st.code(line)
            else:
                st.success("Valid on first attempt: schema and grounding checks passed.")
            for w in result.warnings:
                st.warning(w)
