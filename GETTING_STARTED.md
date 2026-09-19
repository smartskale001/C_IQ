# Getting Started with Contract-IQ

Welcome! This guide takes you from zero to a fully working app. Follow it
top to bottom. Each step has one action and a check so you know it worked.

## 1. What this project does

Contract-IQ reads a property contract and checks it for legal risks.
You upload the contract. AI pulls out the key facts. Those facts are
checked against a legal rulebook. A human reviewer approves, rejects, or
edits each flagged risk. The approved risks become a client-ready summary
email.

No technical detail needed beyond that — the rest of this guide shows you
how to run it yourself.

## 2. Before you start (prerequisites)

You need these three things. Check each one off before continuing.

- [ ] **Python 3.10** installed. (This is the exact version the project
      uses. Check with `python --version`.)
- [ ] **An OpenAI API key.** This is a secret code that lets the app use
      AI. Get one at https://platform.openai.com/api-keys (you may need
      to create a free account first).
- [ ] **Git installed.** This is the tool that downloads the project code.
      Check with `git --version`.

## 3. Clone and set up

Run these commands one at a time, in order. Copy-paste each line.

```bash
git clone <PASTE-YOUR-REPO-URL-HERE>
```

```bash
cd Contract-IQ
```

Create a virtual environment. (This is just a private folder that keeps
this project's tools separate from the rest of your computer.)

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Mac / Linux:

```bash
python3.10 -m venv venv
source venv/bin/activate
```

You will know it worked if your terminal prompt now starts with `(venv)`.

Install the project's tools:

```bash
pip install -r requirements.txt
```

Set up your secret key file:

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

Mac / Linux:

```bash
cp .env.example .env
```

Now open the `.env` file in any text editor. Find the line that says
`OPENAI_API_KEY=`. Paste your OpenAI API key right after the `=` sign.
Save the file. That is the only edit you need to make.

## 4. Start the app

Make sure your `(venv)` prompt is showing, then run:

```bash
python main.py
```

(Windows shortcut: double-click `start.bat` instead — it does the same
thing.)

A successful startup looks like this in your terminal:

```
Database initialized at: .../data/contracts.db
OPENAI_API_KEY loaded successfully
...
Uvicorn running on http://localhost:8000
```

Leave that terminal window open. The app is now running.

Optional, for reference: open **http://localhost:8000/docs** in your
browser. This is a visual page listing every endpoint the app offers.
You don't need it for this guide — everything below uses copy-paste
commands instead.

## 5. Test the full workflow, step by step

Open a **second** terminal window for the commands below. (The first one
must keep running the app.) If you use Mac/Linux and your new terminal
doesn't show `(venv)`, that is fine — `curl` commands don't need it.

The repo already includes a sample contract called `test_contract.pdf`.
Run the next commands from the project folder, so that filename works
as-is.

### Step 1 — Upload and convert the sample contract to text

What you're doing: sending the PDF to the app so it turns it into plain
text it can work with.

```bash
curl -X POST "http://localhost:8000/convert" -F "file=@test_contract.pdf;type=application/pdf"
```

A successful response looks like this (shortened):

```json
{
  "success": true,
  "message": "Document converted successfully",
  "markdown_file_path": "D:\\Contrac_IQ\\tempfolder\\test_contract\\test_contract_extracted.md",
  "conversion_status": "completed"
}
```

✅ You'll know this worked if you see `"success": true` and a
`markdown_file_path`. **Copy that file path** — you need it in Step 2.

### Step 2 — Extract the 12 key facts from it

What you're doing: asking the AI to read the converted text and pull out
facts like the price, deposit, and settlement date.

Replace the path below with the `markdown_file_path` you just copied:

```bash
curl -X POST "http://localhost:8000/extract" -H "Content-Type: application/json" -d "{\"markdown_file_path\": \"D:\\Contrac_IQ\\tempfolder\\test_contract\\test_contract_extracted.md\"}"
```

A successful response looks like this (shortened):

```json
{
  "success": true,
  "message": "Contract fields extracted successfully",
  "extraction_id": 7,
  "extracted_fields": {
    "contract_price": 1285000.0,
    "deposit_amount": 128500.0,
    "subject_to_finance": true
  }
}
```

✅ You'll know this worked if you see an `extraction_id` number and a
`contract_price`. **Write down the `extraction_id`** — you need it in
Steps 3, 4, and 7. (The examples below use `7`; use your own number.)

### Step 3 — Run the AI risk assessment against the rulebook

What you're doing: checking every extracted fact against the legal
rulebook. Each rule that applies becomes one saved "risk".

```bash
curl -X POST "http://localhost:8000/assess-risk" -H "Content-Type: application/json" -d "{\"extraction_id\": 7, \"jurisdiction\": \"VIC\"}"
```

A successful response looks like this (shortened — the real one holds
32 risks):

```json
{
  "success": true,
  "message": "Risk assessment completed",
  "extraction_id": 7,
  "jurisdiction": "VIC",
  "total_risks": 32
}
```

✅ You'll know this worked if you see `"total_risks": 32`. (32 is the
number of rules that apply to Victoria: 8 Victoria rules plus 24
Australia-wide rules.)

### Step 4 — View the list of risks found

What you're doing: reading back the risks the assessment just saved.

```bash
curl "http://localhost:8000/extractions/7/risks"
```

A successful response looks like this (shortened to one risk):

```json
{
  "success": true,
  "extraction_id": 7,
  "total_risks": 32,
  "risks": [
    {
      "rule_id": "VIC-DISC-001",
      "risk_short_desc": "Section 32 evidence missing",
      "assessment_status": "Found",
      "reviewer_status": "pending"
    }
  ]
}
```

✅ You'll know this worked if you see the same `"total_risks": 32`
and every risk says `"reviewer_status": "pending"` (meaning no human
has reviewed them yet).

### Step 5a — Approve one risk

What you're doing: acting as the human reviewer. Approving means "yes,
this risk is real, keep it."

```bash
curl -X PATCH "http://localhost:8000/risks/1" -H "Content-Type: application/json" -d "{\"action\": \"approve\", \"changed_by\": \"you@example.com\"}"
```

A successful response includes:

```json
{
  "rule_id": "VIC-CON-001",
  "reviewer_status": "approved",
  "was_edited": false
}
```

✅ You'll know this worked if you see `"reviewer_status": "approved"`.
(`changed_by` is your name tag — put your own email or name there so
the audit trail records who decided.)

### Step 5b — Reject another risk

What you're doing: rejecting means "no, this one doesn't apply — drop
it from the client email."

```bash
curl -X PATCH "http://localhost:8000/risks/2" -H "Content-Type: application/json" -d "{\"action\": \"reject\", \"changed_by\": \"you@example.com\"}"
```

A successful response includes:

```json
{
  "rule_id": "VIC-CON-002",
  "reviewer_status": "rejected",
  "was_edited": false
}
```

✅ You'll know this worked if you see `"reviewer_status": "rejected"`.

### Step 5c — Edit a third risk

What you're doing: fixing the wording of a risk in your own words. The
risk stays `pending` — editing is separate from approving.

```bash
curl -X PATCH "http://localhost:8000/risks/3" -H "Content-Type: application/json" -d "{\"action\": \"edit\", \"changed_by\": \"you@example.com\", \"risk_short_desc\": \"Section 32 statement requested from vendor\"}"
```

A successful response includes:

```json
{
  "rule_id": "VIC-CON-003",
  "risk_short_desc": "Section 32 statement requested from vendor",
  "reviewer_status": "pending",
  "was_edited": true
}
```

✅ You'll know this worked if you see your new text plus
`"was_edited": true` — and `"reviewer_status"` still says `"pending"`.

### Step 6 — Try to review that same approved risk again (it should fail)

What you're doing: proving the safety guard works. Run the approve
command from Step 5a a second time, on the same risk:

```bash
curl -X PATCH "http://localhost:8000/risks/1" -H "Content-Type: application/json" -d "{\"action\": \"approve\", \"changed_by\": \"you@example.com\"}"
```

You will get an error (`409`), something like:

```json
{
  "detail": "Risk 1 has already been reviewed (approved); only pending risks can be reviewed"
}
```

This is expected behavior, not a bug. Once a human has decided on a
risk, the app locks it so nobody can accidentally overwrite that
decision.

✅ You'll know this worked if you see `409` and the words "already
been reviewed".

### Step 7 — Generate the client summary email

What you're doing: building the plain-text email from the risks you
approved. Rejected and pending risks are left out automatically.

```bash
curl "http://localhost:8000/extractions/7/summary-email"
```

A successful response looks like this:

```json
{
  "success": true,
  "extraction_id": 7,
  "approved_risk_count": 1,
  "message": "Summary email generated with 1 approved risks",
  "email_body": "ContractIQ Risk Summary — test_contract\n\n1. Missing contract date or parties information\n   The extracted fields do not include the contract date or the parties involved...\n\nThis review is a summary and does not replace legal advice on the full contract. Please contact us before signing.\n"
}
```

The `email_body`, written out in full, reads like this:

```
ContractIQ Risk Summary — test_contract

1. Missing contract date or parties information
   The extracted fields do not include the contract date or the parties involved...

This review is a summary and does not replace legal advice on the full contract. Please contact us before signing.
```

✅ You'll know this worked if the email lists only what you approved
(`"approved_risk_count": 1` after the steps above) and ends with the
disclaimer sentence about legal advice.

You have now personally tested every endpoint. Well done!

## 6. Run the automated tests (optional but recommended)

The developers wrote automatic checks that test the app without needing
your API key or the sample contract. To run them, open a terminal in the
project folder with `(venv)` showing, then run:

```bash
pytest
```

When it finishes you will see a line like:

```
35 passed
```

In plain words: all 35 automatic checks passed, meaning everything the
developers built is working correctly right now.

## 7. Run the full end-to-end script (optional)

There is a script that does everything from Section 5 automatically in
one go — all 13 stages (convert, extract, assess, re-run guard, list,
approve, reject, edit, both safety guards, email, audit check, summary).
Doing that by hand would take 10+ manual steps; the script does it in
about a minute and prints exactly what happened at each stage.

With `(venv)` showing, run:

```bash
python scripts/e2e_test.py
```

It stops at the first problem and prints full details, so a clean run
ending in 13 `PASS` lines means the whole pipeline works on your machine.
(Note: unlike the test suite, this script makes real AI calls, so it
uses a small amount of your OpenAI credit.)

## 8. Common problems

| What you see | Likely cause | Fix |
|---|---|---|
| `OPENAI_API_KEY loaded successfully` is missing when the app starts, or `/extract` returns `503` | Your API key is missing or still the placeholder | Open `.env`, paste your real key after `OPENAI_API_KEY=`, save, and restart the app |
| `Port 8000 already in use` (or the app won't start) | Another copy of the app — or something else — is already using that port | Close the other terminal running `python main.py`, or find and stop the program using port 8000, then start again |
| `ModuleNotFoundError: No module named 'fastapi'` (or similar) | You forgot to activate the virtual environment, or skipped installing | Run the activate command from Section 3 (look for `(venv)`), then run `pip install -r requirements.txt` again |
| `File not found` on `/extract` | You pasted a sample path from a guide instead of your own | Use the exact `markdown_file_path` your own `/convert` call returned; if you ran `/cleanup`, convert again first |
| `404` on `/extractions/7/...` | That extraction number doesn't exist in your database | Use your own `extraction_id` from Step 2 (the examples use `7` as an illustration) |
| `409` when re-running `/assess-risk` | You already approved or rejected a risk | This is the safety guard, not an error — see Step 6 |

## 9. What's not built yet

An honest list of what this version does **not** do:

- **No login or user accounts.** Anyone who can reach the app can use every
  endpoint. Do not put this on the public internet as-is.
- **No automatic emailing.** The summary email text is generated for you,
  but you must copy it and send it to the client yourself.
- **Victoria and NSW rules only.** The rulebook covers Victorian contracts,
  New South Wales contracts, and Australia-wide rules. Other states are
  not covered yet.
