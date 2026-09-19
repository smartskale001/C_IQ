# API Usage Examples

Complete examples for using the Document to Markdown Converter API.

## Quick Start

### 1. Start the Server

```bash
python main.py
```

You should see:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete [uvicorn]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2. Convert a Document (in another terminal)

```bash
curl -X POST "http://localhost:8000/convert" \
  -F "file=@/path/to/your/document.pdf"
```

---

## Detailed Examples

### Convert a PDF Document

```bash
curl -X POST "http://localhost:8000/convert" \
  -H "accept: application/json" \
  -F "file=@contract.pdf"
```

**Response:**
```json
{
  "success": true,
  "message": "Document converted successfully",
  "original_file": "contract.pdf",
  "markdown_file_path": "/var/folders/xx/document_uploads/contract_extracted.md",
  "markdown_filename": "contract_extracted.md",
  "temp_directory": "/var/folders/xx/document_uploads",
  "file_size_bytes": 45230,
  "conversion_status": "completed"
}
```

### Convert a Word Document

```bash
curl -X POST "http://localhost:8000/convert" \
  -F "file=@report.docx"
```

### Convert a Scanned PDF (with OCR)

```bash
# Scanned PDFs are automatically detected and processed with OCR
curl -X POST "http://localhost:8000/convert" \
  -F "file=@scanned_invoice.pdf"
```

### Health Check

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "temp_dir": "/var/folders/xx/document_uploads"
}
```

### List All Converted Files

```bash
curl http://localhost:8000/files
```

**Response:**
```json
{
  "success": true,
  "total_files": 3,
  "temp_directory": "/var/folders/xx/document_uploads",
  "files": [
    {
      "filename": "contract_extracted.md",
      "path": "/var/folders/xx/document_uploads/contract_extracted.md",
      "size_bytes": 45230,
      "created": 1694529201.0
    },
    {
      "filename": "report_extracted.md",
      "path": "/var/folders/xx/document_uploads/report_extracted.md",
      "size_bytes": 12456,
      "created": 1694529215.0
    }
  ]
}
```

### Cleanup Temporary Files

```bash
curl -X DELETE http://localhost:8000/cleanup
```

**Response:**
```json
{
  "success": true,
  "message": "Cleaned up 3 items",
  "temp_directory": "/var/folders/xx/document_uploads"
}
```

### Assess Contract Risks Against the Rulebook

```bash
curl -X POST "http://localhost:8000/assess-risk" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"extraction_id": 7, "jurisdiction": "VIC"}'
```

**Response:**
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

Omit `"jurisdiction"` (or send `null`) to use the full rulebook. Re-running is free while all risks are still `pending`; once any risk is reviewed the re-run is blocked with `409`.

### List Assessed Risks for an Extraction

```bash
curl "http://localhost:8000/extractions/7/risks"
```

**Response:**
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

An extraction with no assessment yet returns `"total_risks": 0` and `"risks": []`.

### Review a Risk (Approve / Reject / Edit)

```bash
# Approve
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve", "changed_by": "ashraf@example.com"}'

# Reject
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "reject", "changed_by": "reviewer-1"}'

# Edit (revised text; reviewer_status stays pending, was_edited becomes true)
curl -X PATCH "http://localhost:8000/risks/12" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action": "edit", "changed_by": "ashraf@example.com",
       "risk_short_desc": "Section 32 statement requested from vendor"}'
```

**Response** (the updated risk):
```json
{
  "rule_id": "VIC-DISC-001",
  "risk_short_desc": "Section 32 statement requested from vendor",
  "risk_long_desc": "Request the Section 32 statement before proceeding.",
  "confidence_score": 92,
  "reference": {"page_num": 2, "section_number": "3.2", "section_title": "Disclosure"},
  "assessment_status": "Found",
  "reviewer_status": "pending",
  "was_edited": true
}
```

Only `pending` risks can be reviewed (`409` otherwise); `changed_by` is required.

### Generate the Summary Email

```bash
curl "http://localhost:8000/extractions/7/summary-email"
```

**Response:**
```json
{
  "success": true,
  "extraction_id": 7,
  "approved_risk_count": 2,
  "message": "Summary email generated with 2 approved risks",
  "email_body": "ContractIQ Risk Summary — 123 Example St, Richmond VIC 3121\n\n1. Section 32 statement missing\n   No Section 32 vendor statement was found in the contract pack. Request it from the vendor before signing.\n\n2. Finance condition and deadline unclear\n   The contract is marked subject to finance but no approval deadline is stated. Confirm the lender deadline in writing.\n\nThis review is a summary and does not replace legal advice on the full contract. Please contact us before signing.\n"
}
```

Only `approved` risks appear. With nothing approved yet: `"approved_risk_count": 0`, `"email_body": ""`.

---

## Python Examples

### Basic File Upload

```python
import requests

# Upload and convert
files = {'file': open('document.pdf', 'rb')}
response = requests.post('http://localhost:8000/convert', files=files)

if response.status_code == 200:
    result = response.json()
    print(f"✓ Conversion successful!")
    print(f"Markdown file: {result['markdown_filename']}")
    print(f"File path: {result['markdown_file_path']}")
else:
    print(f"✗ Error: {response.json()['detail']}")
```

### Batch Processing Multiple Files

```python
import requests
from pathlib import Path

# Convert all PDFs in a folder
pdf_folder = Path('./documents')
for pdf_file in pdf_folder.glob('*.pdf'):
    print(f"Processing {pdf_file.name}...")

    with open(pdf_file, 'rb') as f:
        response = requests.post(
            'http://localhost:8000/convert',
            files={'file': f}
        )

        if response.status_code == 200:
            result = response.json()
            print(f"  ✓ Converted to {result['markdown_filename']}")
        else:
            print(f"  ✗ Failed: {response.json()['detail']}")
```

### Save Converted Markdown Locally

```python
import requests
from pathlib import Path

def convert_and_save(document_path, output_dir='./converted'):
    """Convert document and save markdown locally."""

    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    with open(document_path, 'rb') as f:
        response = requests.post(
            'http://localhost:8000/convert',
            files={'file': f}
        )

    if response.status_code == 200:
        result = response.json()
        markdown_path = result['markdown_file_path']

        # Copy to output directory
        import shutil
        local_path = output_dir / result['markdown_filename']
        shutil.copy(markdown_path, local_path)

        print(f"✓ Saved to {local_path}")
        return local_path
    else:
        raise Exception(response.json()['detail'])

# Usage
output = convert_and_save('contract.pdf', './my_markdowns')
```

### Error Handling

```python
import requests

def safe_convert(file_path):
    """Convert with proper error handling."""

    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'http://localhost:8000/convert',
                files={'file': f},
                timeout=30
            )

        if response.status_code == 400:
            error = response.json()['detail']
            print(f"❌ Invalid file: {error}")
            return None

        elif response.status_code == 413:
            print(f"❌ File too large (max 50MB)")
            return None

        elif response.status_code == 500:
            error = response.json()['detail']
            print(f"❌ Server error: {error}")
            print("   Note: Tesseract may need to be installed for OCR")
            return None

        elif response.status_code == 200:
            print(f"✓ Conversion successful!")
            return response.json()['markdown_file_path']

    except requests.exceptions.Timeout:
        print("❌ Request timed out (file too large or API issue)")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")

    return None
```

### Assess and Review Contract Risks

```python
import requests

API = 'http://localhost:8000'
extraction_id = 7

# Assess the extraction against the rulebook (VIC scope → 32 risks)
assess = requests.post(
    f'{API}/assess-risk',
    json={'extraction_id': extraction_id, 'jurisdiction': 'VIC'},
    timeout=120
)
assess.raise_for_status()
print(f"✓ Assessed {assess.json()['total_risks']} risks")

# List the saved risks
risks = requests.get(f'{API}/extractions/{extraction_id}/risks', timeout=30).json()
for item in risks['risks'][:3]:
    print(f"- [{item['assessment_status']}] {item['rule_id']}: {item['risk_short_desc']}")

# Approve a pending risk (changed_by is required).
# Replace risk_id with a real ContractRisk id (see the /risks list output
# combined with your database, or the order risks were saved in).
risk_id = 1
review = requests.patch(
    f'{API}/risks/{risk_id}',
    json={'action': 'approve', 'changed_by': 'you@example.com'},
    timeout=30
)
if review.status_code == 200:
    print(f"✓ Approved (status: {review.json()['reviewer_status']})")
elif review.status_code == 409:
    print("! Already reviewed — only pending risks can be reviewed")

# Client email from approved risks only
email = requests.get(f'{API}/extractions/{extraction_id}/summary-email', timeout=30).json()
print(f"✓ Email covers {email['approved_risk_count']} approved risks")
print(email['email_body'])
```

---

## JavaScript/Node.js Examples

### Basic File Upload

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

async function convertDocument(filePath) {
  const formData = new FormData();
  formData.append('file', fs.createReadStream(filePath));

  try {
    const response = await axios.post(
      'http://localhost:8000/convert',
      formData,
      { headers: formData.getHeaders() }
    );

    console.log('✓ Conversion successful!');
    console.log(`Markdown file: ${response.data.markdown_filename}`);
    console.log(`File path: ${response.data.markdown_file_path}`);

  } catch (error) {
    if (error.response) {
      console.error(`✗ Error: ${error.response.data.detail}`);
    } else {
      console.error(`✗ Error: ${error.message}`);
    }
  }
}

convertDocument('document.pdf');
```

### Fetch API (Browser/Node.js)

```javascript
async function convertDocumentFetch(file) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('http://localhost:8000/convert', {
      method: 'POST',
      body: formData
    });

    if (response.ok) {
      const data = await response.json();
      console.log('✓ Conversion successful!');
      console.log(data);
    } else {
      const error = await response.json();
      console.error(`✗ Error: ${error.detail}`);
    }
  } catch (error) {
    console.error(`✗ Error: ${error.message}`);
  }
}

// Usage with file input
document.getElementById('fileInput').addEventListener('change', (e) => {
  convertDocumentFetch(e.target.files[0]);
});
```

### List and Download Files

```javascript
async function listConvertedFiles() {
  try {
    const response = await fetch('http://localhost:8000/files');
    const data = await response.json();

    console.log(`Total files: ${data.total_files}`);
    console.log(`Directory: ${data.temp_directory}`);

    data.files.forEach(file => {
      console.log(`- ${file.filename} (${file.size_bytes} bytes)`);
    });
  } catch (error) {
    console.error(`Error: ${error.message}`);
  }
}

listConvertedFiles();
```

---

## BASH Script Examples

### Convert All PDFs in Directory

```bash
#!/bin/bash

UPLOAD_DIR="./documents"
API_URL="http://localhost:8000"

echo "Converting all PDFs..."

for pdf_file in "$UPLOAD_DIR"/*.pdf; do
    echo "Processing: $(basename "$pdf_file")"

    response=$(curl -s -X POST "$API_URL/convert" \
        -F "file=@$pdf_file")

    markdown_file=$(echo "$response" | grep -o '"markdown_filename":"[^"]*' | cut -d'"' -f4)
    echo "✓ Converted to: $markdown_file"
done

echo "Done!"
```

### Monitor Conversions

```bash
#!/bin/bash

API_URL="http://localhost:8000"

watch_conversions() {
    while true; do
        echo "=== Converted Files ==="
        curl -s "$API_URL/files" | jq '.files[] | "\(.filename) (\(.size_bytes) bytes)"'
        echo "Refreshing in 5 seconds... (Ctrl+C to stop)"
        sleep 5
    done
}

watch_conversions
```

---

## Testing with the Included Test Script

```bash
python test_api.py
```

This runs automated tests against all API endpoints and shows results.

---

## Common Workflows

### Workflow 1: Convert PDF and Save Locally

```bash
# Convert PDF
response=$(curl -s -X POST http://localhost:8000/convert \
  -F "file=@contract.pdf")

# Extract markdown file path
md_path=$(echo "$response" | grep -o '"markdown_file_path":"[^"]*' | cut -d'"' -f4)

# Copy to local directory
cp "$md_path" "./converted_contract.md"

echo "Saved to ./converted_contract.md"
```

### Workflow 2: Batch Processing with Error Handling

```python
import requests
from pathlib import Path
import json

def batch_convert(source_dir, output_dir):
    """Batch convert all supported documents."""

    source_path = Path(source_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    results = {
        'successful': [],
        'failed': []
    }

    # Support all formats
    for doc_file in list(source_path.glob('*.pdf')) + \
                    list(source_path.glob('*.docx')) + \
                    list(source_path.glob('*.doc')):

        print(f"Converting {doc_file.name}...")

        try:
            with open(doc_file, 'rb') as f:
                response = requests.post(
                    'http://localhost:8000/convert',
                    files={'file': f},
                    timeout=60
                )

            if response.status_code == 200:
                result = response.json()
                # Copy to output
                import shutil
                shutil.copy(
                    result['markdown_file_path'],
                    output_path / result['markdown_filename']
                )
                results['successful'].append(doc_file.name)
                print(f"  ✓ Success")
            else:
                results['failed'].append({
                    'file': doc_file.name,
                    'error': response.json()['detail']
                })
                print(f"  ✗ Failed: {response.json()['detail']}")

        except Exception as e:
            results['failed'].append({
                'file': doc_file.name,
                'error': str(e)
            })
            print(f"  ✗ Error: {str(e)}")

    # Save results
    with open(output_path / 'conversion_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_path / 'conversion_results.json'}")
    return results

# Usage
results = batch_convert('./documents', './converted')
print(f"Successful: {len(results['successful'])}")
print(f"Failed: {len(results['failed'])}")
```

### Workflow 3: Extract → Assess → Review → Summary Email

```bash
#!/bin/bash
# End-to-end risk workflow for one contract. Set EXTRACTION_ID from /extract first.

API_URL="http://localhost:8000"
EXTRACTION_ID=7
REVIEWER="you@example.com"

# 1) Assess the extraction (VIC scope → 32 risks)
curl -s -X POST "$API_URL/assess-risk" \
  -H "Content-Type: application/json" \
  -d "{\"extraction_id\": $EXTRACTION_ID, \"jurisdiction\": \"VIC\"}" | jq '{total_risks}'

# 2) List the saved risks
curl -s "$API_URL/extractions/$EXTRACTION_ID/risks" | jq '.risks[] | "\(.rule_id) [\(.reviewer_status)] \(.risk_short_desc)"'

# 3) Approve one risk (replace 1 with a real ContractRisk id)
curl -s -X PATCH "$API_URL/risks/1" \
  -H "Content-Type: application/json" \
  -d "{\"action\": \"approve\", \"changed_by\": \"$REVIEWER\"}" | jq '{reviewer_status}'

# 4) Client email from approved risks only
curl -s "$API_URL/extractions/$EXTRACTION_ID/summary-email" | jq -r '.email_body'
```

---

## Performance Tips

1. **For Scanned PDFs:** Files with many pages may take longer due to OCR
2. **Batch Processing:** Avoid sending too many simultaneous requests
3. **File Size:** Keep files under 50MB for optimal performance
4. **Cleanup:** Regularly run `DELETE /cleanup` to free disk space
