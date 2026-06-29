# Multi-Source Candidate Data Transformer

A robust, deterministic, and highly configurable data transformation pipeline engineered to ingest candidate data from multiple messy, conflicting structured and unstructured sources, resolve identity conflicts, and project a unified, trustworthy canonical profile.

Designed as part of the **Eightfold Engineering Intern (Jul-Dec 2026) Assignment**.

## 🚀 Features

- **Multi-Source Ingestion:** Ingests structured `ATS JSON blobs` and parses unstructured `Recruiter Notes` text formats out of the box.
- **Data Normalization Layer:** Sanitizes cell and phone strings into strict **E.164 formats** and normalizes tech stack arrays to lowercase canonical string formats.
- **Deterministic Identity Linkage:** Automatically resolves and merges profile records transitively using identity graph matching based on lowercased emails and stripped phone numbers.
- **Explainable Provenance & Confidence System:** Evaluates source credibility using static reliability weights (ATS JSON: `0.95`, Text Notes: `0.50`) and populates a full, line-by-line audit path for every single value.
- **Configurable Runtime Projection:** Features a distinct separation between the internal canonical profile engine and the output schema view. Reshapes, renames, and validates outputs on the fly using runtime JSON configurations.

---

## 🛠️ Project Structure

```text
├── transformer.py          # Core pipeline processing engine and CLI runner
├── README.md               # Setup instructions and documentation
