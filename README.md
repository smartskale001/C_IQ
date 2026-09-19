# Contract-IQ — Document to Markdown Converter & Contract Extraction API

A **FastAPI**-based REST API that converts documents (**PDF, scanned PDF, DOCX, DOC**) into clean Markdown and uses OpenAI to extract **12 contract-specific fields** from the resulting Markdown — all stored in a local **SQLite** database.

```
Upload PDF/DOCX/DOC  -->  /convert  -->  Markdown  -->  /extract  -->  12 field JSON + confidence scores
```

## Risk Assessment Workflow

Once a contract is extracted, the risk pipeline runs end-to-end (mirroring the convert → extract flow above):

```
 /extract  -->  POST /assess-risk  -->  PATCH /risks/{id} (approve / reject / edit)  -->  GET /extractions/{id}/summary-email
     |                 |                                    |                                                    |
 extraction      32 rulebook risks saved              reviewer decision                               plain-text client email
 stored          (VIC/NSW/all rules)                  (pending-only guard)                            (approved risks only)
```

1. **Extract** — `POST /extract` stores the 12 contract fields (returns `extraction_id`).
2. **Assess** — `POST /assess-risk` runs every rulebook rule against the extraction and saves one `ContractRisk` row per rule (32 rows for VIC scope).
3. **Review** — `GET /extractions/{id}/risks` lists the saved risks; `PATCH /risks/{id}` approves, rejects, or edits each risk while it is still `pending` (every action is audit-logged with the reviewer's `changed_by` identity).
4. **Summarise** — `GET /extractions/{id}/summary-email` builds a plain-text client email from the **approved** risks only, ending with the fixed legal disclaimer.

---

## Quick Start (from scratch to running in ~5 minutes)

> Anyone can set this up on their own machine. You only need **Git**, **Python 3.10**, and an **OpenAI API key**. Copy-paste the commands for your OS.

```bash
# 1) Clone the repo and enter the folder
git clone https://github.com/MdAshrafhussain889/Contract-IQ.git
cd Contract-IQ
```

### Windows (PowerShell)

```powershell
# 2) Check Python 3.10 is installed (see Section: Install Python 3.10 if not)
python --version

# 3) Create and activate a virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# 4) Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5) Create your .env file, then set your API key inside it
Copy-Item .env.example .env
notepad .env          # EDIT: set OPENAI_API_KEY=sk-... then Save

# 6) Start the server
python main.py
```

### macOS / Linux

```bash
# 2) Check Python 3.10 is installed (see Section: Install Python 3.10 if not)
python3.10 --version

# 3) Create and activate a virtual environment
python3.10 -m venv venv
source venv/bin/activate

# 4) Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5) Create your .env file, then set your API key inside it
cp .env.example .env
nano .env             # EDIT: set OPENAI_API_KEY=sk-... then Save

# 6) Start the server
python main.py
```

### One-command scripts (optional)

| OS | Command | What it does |
|---|---|---|
| Windows | `setup.bat` then `start.bat` | Creates venv, installs deps, copies `.env.example` → `.env`, then starts the server |
| macOS / Linux | `sh setup.sh` then `sh start_app.sh` | Same as above (loads `.env`, starts the server) |

### You're done when...

1. The terminal shows `Database initialized at: .../data/contracts.db` and `Uvicorn running on http://localhost:8000`
2. Opening **http://localhost:8000/docs** shows the interactive Swagger UI
3. Upload `test_contract.pdf` via **POST /convert** → `200`; then run **POST /extract** on the returned `markdown_file_path` → populated contract fields (this needs your key in `.env`)

---

## Table of Contents

- [Quick Start](#quick-start-from-scratch-to-running-in-5-minutes) *(above)*
- [Features](#features)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Install Python 3.10](#1-install-python-310)
- [Get an OpenAI API Key](#2-get-an-openai-api-key)
- [Install Tesseract (optional, for scanned PDFs)](#3-install-tesseract-optional-for-scanned-pdfs)
- [Clone & Run — Step by Step](#4-clone--run--step-by-step)
- [Database Setup](#database-setup)
- [API Endpoints](#api-endpoints)
- [Testing with Swagger UI](#testing-with-swagger-ui)
- [Running the Test Suite](#running-the-test-suite)
- [Usage Examples](#usage-examples)
- [Error Handling](#error-handling)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Deployment Notes](#deployment-notes)
- [License](#license)

---

## Features

- **Multiple formats** — `.pdf` (text-based), `.pdf` (scanned, via OCR), `.docx` (Word 2007+), `.doc` (Word 97-2003)
- **Resilient PDF pipeline** — `pdfplumber` first, then `PyPDF2` fallback, then OCR for scanned pages
- **LLM contract extraction** — 12 predefined fields with confidence scores and section references
- **Rulebook risk assessment** — `POST /assess-risk` scores an extraction against all 39 merged rulebook rules (VIC / NSW / Australia-wide scopes) and stores one row per rule
- **Reviewer workflow** — list risks, then approve / reject / edit each risk while `pending`; every action is append-only audit-logged with a required `changed_by` reviewer identity
- **Client summary email** — `GET /extractions/{id}/summary-email` renders the approved risks as numbered plain-text points ending with the fixed legal disclaimer
- **Structured storage** — every document gets its own folder (original + Markdown) inside `tempfolder/`
- **SQLite persistence** — all extractions stored with automatic schema migration on startup
- **Security hardening** — filename sanitization, path-confinement (no path traversal), 50 MB upload cap, CORS allow-list, no secrets leaked in errors
- **OpenAPI docs** — auto-generated Swagger UI at `/docs` and ReDoc at `/redoc`

### Extracted fields

| Field | Description |
|---|---|
| `subject_to_lease` | Whether property is subject to lease/tenancy |
| `date_of_tenancy` | Date tenancy begins |
| `contract_price` | Agreed purchase price |
| `deposit_amount` | Required deposit |
| `deposit_due_date` | Deposit payment due date |
| `subject_to_finance` | Finance approval condition |
| `settlement_date` | Settlement/completion date |
| `gst_clause` | GST clause details |
| `terms_contract` | Key contractual terms |
| `default_provisions` | Default/breach provisions |
| `due_date_extension` | Extension provisions |
| `special_conditions` | Special/unique clauses |

---

## Project Structure

```
Contract-IQ/
├── main.py                      # FastAPI application & all routes (entry point)
├── db.py                        # SQLite setup, init_db(), lightweight migrations
├── document_converter.py        # PDF/DOCX/DOC -> Markdown conversion + OCR fallback
├── prompts.py                   # LLM prompt templates for extraction
├── models/
│   ├── contract_extract.py      # SQLModel table ContractExtract
│   └── schemas.py               # Pydantic schemas (responses, extracted parameters)
├── services/
│   └── contract_extractor.py    # OpenAI call, validation, markdown reading
├── tests/
│   ├── conftest.py              # In-memory DB fixture + mocked OpenAI client
│   └── test_api.py              # 11 pytest tests (API behavior)
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Test dependencies (includes -r requirements.txt)
├── pytest.ini                   # Pytest configuration
├── .env.example                 # Sample environment file (copy to .env)
├── .gitignore
├── setup.bat  /  start.bat      # Windows one-command setup / start
├── setup.sh   /  start_app.sh   # macOS / Linux one-command setup / start
├── data/                        # Auto-created: contracts.db (SQLite)
├── tempfolder/                  # Auto-created: uploads + generated markdown
├── test_contract.pdf            # Sample contract for quick testing
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.109 |
| ASGI server | Uvicorn 0.27 |
| ORM | SQLModel / SQLAlchemy 2 |
| Database | SQLite (file: `data/contracts.db`, auto-created) |
| PDF text | pdfplumber + PyPDF2 fallback |
| OCR (scanned PDFs) | Tesseract + pytesseract + pdf2image (optional) |
| DOCX | python-docx |
| LLM | OpenAI API v1 (`openai==1.28.1`) |
| Response validation | Pydantic v2 |

---

## Prerequisites

- **Git** installed ([git-scm.com](https://git-scm.com/))
- **Python 3.10** (see below for exact install steps)
- **OpenAI API key** ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))
- **(Optional)** Tesseract OCR for scanned PDFs

---

## 1. Install Python 3.10

Verify what you have first:

```bash
python --version     # Windows
python3 --version    # macOS / Linux
```

> **Recommended version: Python 3.10.x** — this project is developed and tested on **3.10.0**.
> It also works on 3.11; avoid 3.13+ until dependencies are updated.

### Windows

**Option A — Microsoft Store (easiest):**
1. Open the Microsoft Store and search **“Python 3.10”**
2. Click **Get** / **Install** ("Python 3.10" by the Python Software Foundation)

**Option B — python.org:**
1. Download "Windows installer (64-bit)" from https://www.python.org/downloads/windows/ (pick the 3.10.x release)
2. Run the installer
3. **IMPORTANT:** tick **“Add Python 3.10 to PATH”** at the bottom of the first screen
4. Click **Install Now**

**Option C — winget:**
```powershell
winget install Python.Python.3.10
```

Verify:
```powershell
py -3.10 --version
# OR if Python is on PATH:
python --version
```

### macOS

Via Homebrew:
```bash
brew install python@3.10
export PATH="/opt/homebrew/opt/python@3.10/bin:$PATH"   # Apple Silicon
export PATH="/usr/local/opt/python@3.10/bin:$PATH"      # Intel
python3.10 --version
```

### Linux (Ubuntu / Debian)

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.10 python3.10-venv python3.10-dev
python3.10 --version
```

### All platforms — pyenv alternative

```bash
# install pyenv first, then:
pyenv install 3.10.0
pyenv global 3.10.0   # or: pyenv local 3.10.0  inside the repo
python --version      # -> Python 3.10.0
```

---

## 2. Get an OpenAI API Key

1. Sign in at https://platform.openai.com
2. Go to **API Keys** → **Create new secret key**
3. Copy the key. It starts with `sk-`.

> Never share the key, never commit it, and keep it only in your local `.env`
> (already ignored by git). If you paste it into a chat, revoke/rotate it.

---

## 3. Install Tesseract (optional, for scanned PDFs)

OCR is only invoked when a PDF contains **no selectable text**. Text PDFs don't need Tesseract.

| OS | Command / Link |
|---|---|
| Windows | Installer from https://github.com/UB-Mannheim/tesseract/wiki |
| macOS | `brew install tesseract` |
| Ubuntu/Debian | `sudo apt-get install tesseract-ocr` |

If Tesseract is missing, scanned PDFs return a clear `500` ("Tesseract is not installed") instead of crashing.

---

## 4. Clone & Run — Step by Step

### Step 1 — Clone the repository

```bash
git clone https://github.com/MdAshrafhussain889/Contract-IQ.git
cd Contract-IQ
```

> New here? If you followed the [Quick Start](#quick-start-from-scratch-to-running-in-5-minutes) section above, skip straight to `setup.bat` (Windows) or `sh setup.sh` (macOS/Linux). The detailed manual steps below are exactly what those scripts do automatically.

### Step 2 — Create a virtual environment

```bash
# Windows
python -m venv venv

# macOS / Linux (use python3.10 if your default Python isn't 3.10)
python3.10 -m venv venv
```

### Step 3 — Activate it

```bash
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (Command Prompt / Git Bash)
venv\Scripts\activate.bat

# macOS / Linux
source venv/bin/activate
```

You should now see `(venv)` at the start of your prompt.

### Step 4 — Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Optional** — install test dependencies too:

```bash
pip install -r requirements-dev.txt
```

### Step 5 — Configure environment

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Then edit `.env` and set your OpenAI key:

```ini
OPENAI_API_KEY=sk-your_real_key_here
```

Minimum working `.env`:

```ini
OPENAI_API_KEY=sk-your_real_key_here
LOG_LEVEL=INFO
```

The `DATABASE_URL` needs **no** setup — SQLite is configured automatically to `data/contracts.db`.

### Step 6 — Start the API

```bash
python main.py
```

Expected output:

```
Database initialized at: D:\Contrac_IQ\data\contracts.db
OPENAI_API_KEY loaded successfully
...
Uvicorn running on http://localhost:8000
```

> On macOS/Linux, `start_app.sh` does the same thing (loads `.env` + starts the app).
> `setup.sh` automates steps 2-5 on macOS/Linux.

### Step 7 — Verify

Open in your browser:

| URL | What it is |
|---|---|
| http://localhost:8000/docs | Swagger UI (interactive) |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/health | Health JSON |

You should see:

```json
{"status": "healthy", "temp_dir": "D:\\Contrac_IQ\\tempfolder"}
```

---

## Database Setup

There is **no external database server** — the API uses **SQLite**, a single file that is fully created and managed on first run.

### What happens on startup

1. `db.py` creates the `data/` folder if missing.
2. `init_db()` runs `SQLModel.metadata.create_all(...)` to create missing tables.
3. A **lightweight auto-migration** step adds any missing columns to existing tables — so older databases keep working without manual `ALTER TABLE`.
4. Your database file lives at: `data/contracts.db`.

### What's stored

The `contractextract` table stores every `/extract` call: the source markdown filename, folder path, all 12 extracted fields (JSON), extracted parameters (name/value/confidence/section reference), and a timestamp.

### How to reset the database

Stop the server, then:

```bash
# Windows PowerShell
Remove-Item data\contracts.db

# macOS / Linux
rm data/contracts.db
```

Restart `python main.py` — a fresh database is recreated automatically. (The database file is gitignored and never committed.)

> For PostgreSQL/MySQL in production, swap the `DATABASE_URL` in `db.py` — the models are SQLModel/SQLAlchemy so they work with any supported backend.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | API info + endpoint list |
| GET | `/health` | Health check + temp dir |
| POST | `/convert` | Upload document -> Markdown (multipart `file` field) |
| GET | `/files` | List all converted document folders |
| DELETE | `/cleanup` | Delete all folders in the temp directory |
| POST | `/extract` | Extract 12 contract fields from a Markdown file |
| GET | `/extractions` | List stored extractions (newest first) |
| GET | `/extractions/{id}` | Fetch a single extraction |
| POST | `/assess-risk` | Assess an extraction against the rulebook (one risk row per rule) |
| GET | `/extractions/{id}/risks` | List stored risks for an extraction (insertion order) |
| PATCH | `/risks/{id}` | Approve, reject, or edit a single pending risk |
| GET | `/extractions/{id}/summary-email` | Plain-text client email from approved risks only |

### Convert a document

```bash
curl -X POST "http://localhost:8000/convert" \
  -H "accept: application/json" \
  -F "file=@test_contract.pdf;type=application/pdf"
```

Response (200):

```json
{
  "success": true,
  "message": "Document converted successfully",
  "original_file": "test_contract.pdf",
  "original_file_path": "D:\\Contrac_IQ\\tempfolder\\test_contract\\test_contract.pdf",
  "original_file_size_bytes": 8486,
  "markdown_filename": "test_contract_extracted.md",
  "markdown_file_path": "D:\\Contrac_IQ\\tempfolder\\test_contract\\test_contract_extracted.md",
  "markdown_file_size_bytes": 7329,
  "file_folder": "D:\\Contrac_IQ\\tempfolder\\test_contract",
  "folder_name": "test_contract",
  "temp_directory": "D:\\Contrac_IQ\\tempfolder",
  "conversion_status": "completed"
}
```

### Extract contract fields

The `markdown_file_path` must be an existing `.md` file **inside `tempfolder/`**.

```bash
curl -X POST "http://localhost:8000/extract" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"markdown_file_path": "D:\\Contrac_IQ\\tempfolder\\test_contract\\test_contract_extracted.md"}'
```

Response (200):

```json
{
  "success": true,
  "message": "Contract fields extracted successfully",
  "extraction_id": 7,
  "extracted_fields": {
    "subject_to_lease": "The Property is subject to an existing lease or tenancy arrangement.",
    "contract_price": 1285000.0,
    "deposit_amount": 128500.0,
    "subject_to_finance": true,
    "gst_clause": "...$1,285,000 is GST inclusive...",
    ...
  },
  "extracted_parameters": [
    {
      "parameter_name": "contract_price",
      "parameter_value": "1285000",
      "confidence_score": 100,
      "reference": {"section_number": "2", "section_title": "PURCHASE PRICE AND PAYMENT TERMS"}
    }
  ],
  "timestamp": "2026-09-17T10:15:59.319622"
}
```

> If you extract from a **non-contract** document (e.g. a job form), fields come back `null` — that's correct behaviour, not an error.

### Assess contract risks

Runs every rulebook rule in scope against a stored extraction and saves one `ContractRisk` row per rule (32 rows for VIC scope: 8 VIC + 24 Australia-wide).

```bash
curl -X POST "http://localhost:8000/assess-risk" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"extraction_id": 7, "jurisdiction": "VIC"}'
```

- `jurisdiction` is optional: `"VIC"`, `"NSW"`, or omit it. An explicit override wins; otherwise the jurisdiction is derived from the extraction's stored fields; otherwise the full rulebook is used.
- Each returned risk has `rule_id`, `risk_short_desc`, `risk_long_desc`, `confidence_score` (0-100), `reference` (page/section), `assessment_status` (`Found` | `Not Found` | `Needs Attention` | `Not Applicable`), `reviewer_status` (`pending`), and `was_edited` (`false`).

Response (200, abbreviated — `risks` holds one item per rule):

```json
{
  "success": true,
  "message": "Risk assessment completed",
  "extraction_id": 7,
  "jurisdiction": "VIC",
  "risks": [
    {
      "rule_id": "VIC-DISC-001",
      "risk_short_desc": "Section 32 evidence missing",
      "risk_long_desc": "Request the Section 32 statement before proceeding.",
      "confidence_score": 92,
      "reference": {"page_num": 2, "section_number": "3.2", "section_title": "Disclosure"},
      "assessment_status": "Found",
      "reviewer_status": "pending",
      "was_edited": false
    }
  ],
  "total_risks": 32,
  "timestamp": "2026-09-18T10:00:00"
}
```

**409 re-run guard** — re-running is free while existing risks are all still `pending` (untouched rows are replaced). If **any** risk for the extraction has already been reviewed (`approved`/`rejected`), the re-run is blocked with `409` to protect reviewer work, and the old audit entries are kept (audit log is append-only and never deleted).

### List assessed risks

```bash
curl "http://localhost:8000/extractions/7/risks"
```

Response (200) — same `RiskItem` shape as `/assess-risk`, in insertion order:

```json
{
  "success": true,
  "extraction_id": 7,
  "total_risks": 32,
  "risks": [
    {
      "rule_id": "VIC-DISC-001",
      "risk_short_desc": "Section 32 evidence missing",
      "risk_long_desc": "Request the Section 32 statement before proceeding.",
      "confidence_score": 92,
      "reference": {"page_num": 2, "section_number": "3.2", "section_title": "Disclosure"},
      "assessment_status": "Found",
      "reviewer_status": "pending",
      "was_edited": false
    }
  ]
}
```

> If the extraction exists but no assessment has been run yet, this returns `200` with `"total_risks": 0` and `"risks": []` — an empty list, not a `404`. A `404` is only returned when the `extraction_id` itself does not exist.

### Review a risk (approve / reject / edit)

All three actions require the risk to still be `pending` — anything already `approved`/`rejected` returns `409`. `changed_by` (reviewer identifier, free text) is **required** on every action so the audit trail always records who decided. Edit updates the text fields and sets `was_edited: true` **without** changing `reviewer_status`; approve/reject are separate actions.

Approve:

```bash
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve", "changed_by": "ashraf@example.com"}'
```

Reject:

```bash
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "reject", "changed_by": "reviewer-1"}'
```

Edit (at least one of `risk_short_desc` / `risk_long_desc` required; unchanged values are skipped):

```bash
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "edit", "changed_by": "ashraf@example.com",
       "risk_short_desc": "Section 32 statement requested from vendor"}'
```

Response (200) — the updated `RiskItem` (same shape as the `/risks` list entries), e.g. `"reviewer_status": "approved"` after an approve, or `"was_edited": true` with the revised text after an edit. Every change appends an `AuditLog` entry (`approved` / `rejected` / `edited` with `field_changed`, old `ai_value` and new `human_value` for edits).

### Generate the summary email

Builds a plain-text client email from the **approved** risks only — pending and rejected risks never appear. Each approved risk becomes a numbered point (`risk_short_desc` as the heading, `risk_long_desc` as the explanation), and the body always ends with the fixed disclaimer line.

```bash
curl "http://localhost:8000/extractions/7/summary-email"
```

Response (200):

```json
{
  "success": true,
  "extraction_id": 7,
  "approved_risk_count": 2,
  "message": "Summary email generated with 2 approved risks",
  "email_body": "ContractIQ Risk Summary — 123 Example St, Richmond VIC 3121\n\n1. Section 32 statement missing\n   No Section 32 vendor statement was found in the contract pack. Request it from the vendor before signing.\n\n2. Finance condition and deadline unclear\n   The contract is marked subject to finance but no approval deadline is stated. Confirm the lender deadline in writing.\n\nThis review is a summary and does not replace legal advice on the full contract. Please contact us before signing.\n"
}
```

> If the extraction exists but nothing is approved yet, this returns `200` with `"approved_risk_count": 0`, `"email_body": ""`, and a `message` explaining that at least one risk must be approved first — never a `404`.

---

## Testing with Swagger UI

1. Start the server: `python main.py`
2. Open **http://localhost:8000/docs**
3. Click **Try it out** on any endpoint, fill in the parameters, click **Execute**.

Suggested flow:

1. **POST `/convert`** — upload `test_contract.pdf`. Note the returned `markdown_file_path`.
2. **GET `/files`** — confirm the folder was created.
3. **POST `/extract`** — paste the exact `markdown_file_path` from step 1 into `{"markdown_file_path": "..."}`. Expect `200` with populated fields. Note the returned `extraction_id`.
4. **GET `/extractions`** / **GET `/extractions/{id}`** — see stored records.
5. **POST `/assess-risk`** — send `{"extraction_id": <id from step 3>, "jurisdiction": "VIC"}`. Expect `200` with 32 risks.
6. **GET `/extractions/{id}/risks`** — confirm the saved risks list.
7. **PATCH `/risks/{id}`** — send `{"action": "approve", "changed_by": "you@example.com"}` on one risk; try `"edit"` with a revised `risk_short_desc` on another.
8. **GET `/extractions/{id}/summary-email`** — see the client email built from approved risks only.
9. **DELETE `/cleanup`** — clear the temp folder (do this last, it deletes converted files).

Negative-path checks you can do in Swagger:

| Request | Expected status |
|---|---|
| Upload `.txt` or `.prn` | `400` Unsupported file format |
| Upload empty/0-byte PDF | `400` Document appears to be empty |
| `/extract` with a path outside `tempfolder/` | `400` must point inside the temporary directory |
| `/extract` with a `.txt` path | `400` must be markdown (.md) |
| `/extract` with a missing file | `400` File not found |
| `/extract` without `OPENAI_API_KEY` set | `503` |
| `/extractions/999999` | `404` |
| `/extractions/abc` | `422` |
| `/assess-risk` with unknown `extraction_id` | `404` |
| `/assess-risk` with `"jurisdiction": "TAS"` | `400` must be `VIC`, `NSW`, or omitted |
| `/assess-risk` re-run after a risk was reviewed | `409` already reviewed |
| `/extractions/7/risks` before any assessment | `200` with `"risks": []` (not a 404) |
| `/risks/999999` with `PATCH` | `404` |
| `PATCH /risks/{id}` on an approved/rejected risk | `409` only pending risks can be reviewed |
| `PATCH /risks/{id}` with blank `changed_by` | `400` reviewer identity required |
| `PATCH /risks/{id}` edit with no text fields | `400` requires `risk_short_desc` or `risk_long_desc` |
| `/extractions/7/summary-email` with nothing approved | `200` with `"email_body": ""` (not a 404) |

---

## Running the Test Suite

The project ships a pytest suite (35 tests) using an **in-memory SQLite database** and a **mocked OpenAI client** — no key or real network needed.

```bash
pip install -r requirements-dev.txt
pytest
```

Expected output:

```
35 passed in ~1-5s
```

What it covers: health/root endpoints, empty & corrupt PDF handling, valid conversion (PyPDF2 fallback), path-traversal blocking, temp-folder confinement, wrong-extension rejection, missing-key 503, full extraction + storage round-trip, the extractions list endpoint, rulebook loading, risk-table and audit-log models, the risks list endpoint (ordering, empty list, 404), the risk review endpoint (approve / reject / edit, audit entries, 404 / 409 / 400 guards), and the summary-email endpoint (approved-only filtering, empty case, 404).

---

## Usage Examples

### Python

```python
import requests

# Convert
files = {"file": open("test_contract.pdf", "rb")}
conv = requests.post("http://localhost:8000/convert", files=files).json()
md_path = conv["markdown_file_path"]  # full path inside tempfolder/

# Extract
resp = requests.post(
    "http://localhost:8000/extract",
    json={"markdown_file_path": md_path},
).json()
print(resp["extracted_fields"]["contract_price"])
print(resp["extracted_parameters"])
extraction_id = resp["extraction_id"]

# Assess against the rulebook (VIC scope → 32 risks)
assess = requests.post(
    "http://localhost:8000/assess-risk",
    json={"extraction_id": extraction_id, "jurisdiction": "VIC"},
).json()
print(assess["total_risks"])
first_risk_id = 1  # replace with a real ContractRisk id, e.g. from GET /extractions/{id}/risks

# Review: approve one risk (changed_by is required)
review = requests.patch(
    f"http://localhost:8000/risks/{first_risk_id}",
    json={"action": "approve", "changed_by": "you@example.com"},
).json()
print(review["reviewer_status"])

# Client email from approved risks only
email = requests.get(
    f"http://localhost:8000/extractions/{extraction_id}/summary-email"
).json()
print(email["email_body"])
```

### JavaScript (browser / node)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('http://localhost:8000/convert', { method: 'POST', body: formData })
  .then(r => r.json())
  .then(data => console.log(data.markdown_file_path));
```

### cURL

```bash
curl http://localhost:8000/health
curl http://localhost:8000/files
curl -X DELETE http://localhost:8000/cleanup
```

---

## Error Handling

| Status | Meaning | How to fix |
|---|---|---|
| `400` | Unsupported file format | Use `.pdf`, `.docx`, or `.doc` |
| `400` | Empty / malformed document | Provide a valid, un-corrupted file |
| `400` | Extraction path invalid | `markdown_file_path` must be an existing `.md` inside `tempfolder/` |
| `404` | Extraction / risk not found | Use a valid `extraction_id` / `risk_id` (check `/extractions` or `/extractions/{id}/risks`) |
| `400` | Invalid jurisdiction override | `jurisdiction` must be `VIC`, `NSW`, or omitted |
| `400` | Invalid review request | `changed_by` must be non-empty; `edit` needs `risk_short_desc` or `risk_long_desc` |
| `409` | Already reviewed | Re-running `/assess-risk` or `PATCH`ing a non-`pending` risk is blocked to protect reviewer work |
| `413` | File too large | Keep uploads under the 50 MB limit |
| `422` | Validation error | Check request body/parameter format |
| `500` | Internal conversion/extraction error | Tesseract missing (OCR), or check server logs |
| `503` | Extraction not configured | Set `OPENAI_API_KEY` in `.env` and restart |

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(none)* | Required for `/extract` and `/assess-risk`. Missing/placeholder → `503`. |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated browser-origin allow-list |

Other fixed settings (see `main.py`):

- Upload storage: `tempfolder/` in the project directory (auto-created)
- Max upload size: **50 MB** (streamed, chunked check)
- `DATABASE_URL`: SQLite at `data/contracts.db`

---

## Troubleshooting

**`OPENAI_API_KEY loaded successfully` is missing on startup**
→ Key is absent or is still the placeholder. Edit `.env` and restart.

**`/extract` returns 503**
→ `OPENAI_API_KEY` missing/placeholder, or the server was started before you set it. Restart `python main.py`.

**`TesseractNotFoundError: ... not installed or it's not in your PATH`**
→ Scanned PDFs need Tesseract. Install it (see section 3, above) and make sure `tesseract` is on `PATH`. For text PDFs this error never occurs.

**`File not found: D:\...\tempfolder\contract\...` on `/extract`**
→ You used a sample path from the docs. Use the exact `markdown_file_path` returned by `/convert`, and re-convert first if you ran `/cleanup`.

**SQLite database not created**
→ `db.py:init_db()` runs at startup and logs `Database initialized at: ...`. Check the `data/` folder exists and is writable.

**Port 8000 already in use**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

**`ModuleNotFoundError` after clone**
→ You are outside the venv, or dependencies weren't installed. Re-run steps 2-4 of [Clone & Run](#4-clone--run--step-by-step).

---

## Deployment Notes

- Run under a process manager (systemd / PM2 / Task Scheduler) or:
  ```bash
  uvicorn main:app --host 0.0.0.0 --port 8000
  ```
- Set `CORS_ORIGINS` to your frontend origin(s).
- Put the API behind a reverse proxy (Nginx/Caddy) for TLS.
- Use a `requirements.txt`-pinned environment in production; the database auto-migrates on startup.

---

## License

MIT