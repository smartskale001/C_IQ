"""
FastAPI endpoint for document to Markdown conversion.
Accepts PDF, DOCX, and DOC files and converts them to Markdown format.
"""

import os
import shutil
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging
from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlmodel import Session, select
from dotenv import load_dotenv

# Load environment variables from .env file
# Use absolute path to ensure .env is loaded regardless of working directory
_env_file = Path(__file__).parent / ".env"
load_dotenv(_env_file, override=True)

# Verify API key is loaded
_api_key_check = os.getenv("OPENAI_API_KEY")
if _api_key_check and _api_key_check != "your_openai_api_key_here":
    print("OPENAI_API_KEY loaded successfully", flush=True)
else:
    print("WARNING: OPENAI_API_KEY not found in environment", flush=True)

from document_converter import (
    DocumentConverter,
    DocumentConversionError,
    ConversionServiceError,
)
from models.contract_extract import ContractExtract, ContractExtractResponse, ContractExtractBase
from models.schemas import ExtractedParameter, Reference, RiskItem
from models.risk import ContractRisk
from models.audit import AuditLog
import models.risk  # noqa: F401  (registers the contract_risks table)  # noqa: E402
import models.audit  # noqa: F401  (registers the audit_log table)  # noqa: E402
from services.contract_extractor import (
    get_extractor,
    ContractExtractionError,
    InvalidMarkdownFileError,
    MissingApiKeyError,
)
from services.risk_assessor import assess_risks, RiskAssessmentError
from db import init_db, get_session, engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the database (creates tables and applies lightweight migrations)
# Module-level so it runs whether launched via `python main.py` or `uvicorn main:app`.
init_db()

# ==================== Pydantic Models ====================

def _example(value):
    """Build a Pydantic v2 json_schema_extra dict carrying a Swagger example."""
    return {"example": value}


class RootResponse(BaseModel):
    """Root endpoint response model."""
    message: str = Field(..., json_schema_extra=_example("Document to Markdown Converter API"))
    status: str = Field(..., json_schema_extra=_example("running"))
    endpoints: dict = Field(
        ...,
        json_schema_extra=_example({
            "POST /convert": "Upload document and convert to markdown",
            "GET /health": "Health check",
            "GET /files": "List all converted files",
            "DELETE /cleanup": "Delete all temporary files",
            "POST /extract": "Extract contract fields from a markdown file",
            "GET /extractions": "List all stored extractions",
            "GET /extractions/{id}": "Get a stored extraction by ID",
            "POST /assess-risk": "Assess contract risks against the rulebook",
            "GET /extractions/{extraction_id}/risks": "List risks assessed for an extraction",
            "PATCH /risks/{risk_id}": "Review a contract risk (approve, reject, or edit while pending)",
            "GET /extractions/{extraction_id}/summary-email": "Generate a summary email body for an extraction"
        })
    )


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., json_schema_extra=_example("healthy"))
    temp_dir: str = Field(..., json_schema_extra=_example("tempfolder"))


class ConvertSuccessResponse(BaseModel):
    """Successful document conversion response model."""
    success: bool = Field(..., json_schema_extra=_example(True))
    message: str = Field(..., json_schema_extra=_example("Document converted successfully"))
    original_file: str = Field(..., json_schema_extra=_example("contract.pdf"))
    original_file_path: str = Field(
        ...,
        json_schema_extra=_example("tempfolder/contract/contract.pdf")
    )
    original_file_size_bytes: int = Field(..., json_schema_extra=_example(154230))
    markdown_filename: str = Field(..., json_schema_extra=_example("contract_extracted.md"))
    markdown_file_path: str = Field(
        ...,
        json_schema_extra=_example("tempfolder/contract/contract_extracted.md")
    )
    markdown_file_size_bytes: int = Field(..., json_schema_extra=_example(6919))
    file_folder: str = Field(
        ...,
        json_schema_extra=_example("tempfolder/contract")
    )
    folder_name: str = Field(..., json_schema_extra=_example("contract"))
    temp_directory: str = Field(
        ...,
        json_schema_extra=_example("tempfolder")
    )
    conversion_status: str = Field(..., json_schema_extra=_example("completed"))


class FileInfo(BaseModel):
    """Information about a converted file."""
    folder_name: str = Field(..., json_schema_extra=_example("Mujeeb_CV_6"))
    folder_path: str = Field(
        ...,
        json_schema_extra=_example("tempfolder/Mujeeb_CV_6")
    )
    original_file: Optional[str] = Field(None, json_schema_extra=_example("Mujeeb_CV_6.pdf"))
    original_file_size_bytes: int = Field(..., json_schema_extra=_example(154230))
    markdown_file: Optional[str] = Field(None, json_schema_extra=_example("Mujeeb_CV_6_extracted.md"))
    markdown_file_size_bytes: int = Field(..., json_schema_extra=_example(6919))
    total_files: int = Field(..., json_schema_extra=_example(2))
    created: float = Field(..., json_schema_extra=_example(1694529201.0))


class ListFilesResponse(BaseModel):
    """List all converted files response model."""
    success: bool = Field(..., json_schema_extra=_example(True))
    total_folders: int = Field(..., json_schema_extra=_example(3))
    temp_directory: str = Field(
        ...,
        json_schema_extra=_example("tempfolder")
    )
    folders: List[FileInfo] = Field(
        ...,
        json_schema_extra=_example([
            {
                "folder_name": "contract",
                "folder_path": "tempfolder/contract",
                "original_file": "contract.pdf",
                "original_file_size_bytes": 154230,
                "markdown_file": "contract_extracted.md",
                "markdown_file_size_bytes": 6919,
                "total_files": 2,
                "created": 1694529201.0
            }
        ])
    )


class CleanupResponse(BaseModel):
    """Cleanup response model."""
    success: bool = Field(..., json_schema_extra=_example(True))
    message: str = Field(..., json_schema_extra=_example("Cleaned up 5 items"))
    temp_directory: str = Field(
        ...,
        json_schema_extra=_example("tempfolder")
    )


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str = Field(
        ...,
        json_schema_extra=_example("Unsupported file format: .txt. Supported formats: .doc, .docx, .pdf")
    )


# ==================== Extraction Response Models ====================

class ExtractRequest(BaseModel):
    """Request model for contract field extraction."""
    markdown_file_path: str = Field(
        ...,
        json_schema_extra=_example("tempfolder/contract/contract_extracted.md"),
        description="Full path to the markdown file to extract from (must be inside the temp directory)"
    )


class ExtractedFieldsResponse(BaseModel):
    """Response model for extracted contract fields."""
    success: bool = Field(..., json_schema_extra=_example(True))
    message: str = Field(..., json_schema_extra=_example("Contract fields extracted successfully"))
    extraction_id: int = Field(..., json_schema_extra=_example(1))
    extracted_fields: ContractExtractResponse = Field(
        ...,
        description="Extracted contract fields with database record ID"
    )
    extracted_parameters: Optional[List[ExtractedParameter]] = Field(
        None,
        description="Structured extracted parameters with confidence scores and references"
    )
    timestamp: str = Field(..., json_schema_extra=_example("2026-09-12T19:30:00"))


class ExtractionListResponse(BaseModel):
    """Response model for listing extractions."""
    success: bool = Field(..., json_schema_extra=_example(True))
    total_extractions: int = Field(..., json_schema_extra=_example(5))
    extractions: List[ContractExtractResponse] = Field(
        ...,
        description="List of all extracted contracts"
    )


class AssessRiskRequest(BaseModel):
    """Request model for risk assessment."""
    extraction_id: int = Field(
        ...,
        json_schema_extra=_example(1),
        description="ID of an existing extraction to assess against the rulebook"
    )
    jurisdiction: Optional[str] = Field(
        None,
        json_schema_extra=_example("VIC"),
        description="Jurisdiction scope: \"VIC\", \"NSW\", or omit for the full rulebook"
    )


class AssessRiskResponse(BaseModel):
    """Response model for risk assessment."""
    success: bool = Field(..., json_schema_extra=_example(True))
    message: str = Field(..., json_schema_extra=_example("Risk assessment completed"))
    extraction_id: int = Field(..., json_schema_extra=_example(1))
    jurisdiction: Optional[str] = Field(
        None,
        json_schema_extra=_example("VIC"),
        description="Jurisdiction scope used for the assessment (derived or override)"
    )
    risks: List[RiskItem] = Field(
        ...,
        description="Validated risk items, one per rulebook rule"
    )
    total_risks: int = Field(..., json_schema_extra=_example(32))
    timestamp: str = Field(..., json_schema_extra=_example("2026-09-18T10:00:00"))


class RiskListResponse(BaseModel):
    """Response model for listing stored risks for one extraction."""
    success: bool = Field(..., json_schema_extra=_example(True))
    extraction_id: int = Field(..., json_schema_extra=_example(1))
    total_risks: int = Field(..., json_schema_extra=_example(32))
    risks: List[RiskItem] = Field(
        ...,
        description="Stored risk items, one per rulebook rule, in insertion order"
    )


class RiskReviewAction(str, Enum):
    """Reviewer action taken against a single pending risk."""
    approve = "approve"
    reject = "reject"
    edit = "edit"


class RiskUpdateRequest(BaseModel):
    """Request model for reviewing a single contract risk."""
    action: RiskReviewAction = Field(
        ...,
        description="Reviewer action: \"approve\", \"reject\", or \"edit\""
    )
    changed_by: str = Field(
        ...,
        min_length=1,
        json_schema_extra=_example("ashraf@example.com"),
        description="Reviewer identifier (free text; no auth system yet)"
    )
    risk_short_desc: Optional[str] = Field(
        None,
        json_schema_extra=_example("Section 32 statement requested from vendor"),
        description="Revised 1-line summary (action=\"edit\" only)"
    )
    risk_long_desc: Optional[str] = Field(
        None,
        json_schema_extra=_example("Vendor to provide the Section 32 statement before exchange."),
        description="Revised full explanation (action=\"edit\" only)"
    )


class SummaryEmailResponse(BaseModel):
    """Response model for a generated summary-email body."""
    success: bool = Field(..., json_schema_extra=_example(True))
    extraction_id: int = Field(..., json_schema_extra=_example(1))
    approved_risk_count: int = Field(
        ...,
        json_schema_extra=_example(6),
        description="Number of approved risks included in the email body"
    )
    message: str = Field(
        ...,
        json_schema_extra=_example("Summary email generated for 6 approved risks"),
        description="Human-readable status message; explains the empty case clearly"
    )
    email_body: str = Field(
        ...,
        json_schema_extra=_example(
            "ContractIQ risk summary for 123 Example St, Richmond VIC 3121\n"
            "\n"
            "1. Deposit and finance\n"
            "   Finance clause and deposit arrangement assessed against the rulebook.\n"
            "2. Settlement date\n"
            "   Settlement date and extension provisions assessed against the rulebook.\n"
            "\n"
            "This review is a summary and does not replace legal advice on the full "
            "contract. Please contact us before signing."
        ),
        description="Plain-text email body; empty when no approved risks exist"
    )


# Initialize FastAPI app
app = FastAPI(
    title="Document to Markdown Converter API",
    description="Convert PDF, DOCX, and DOC files to Markdown format with sample payloads for developer reference",
    version="1.0.0",
    contact={
        "name": "API Support",
        "url": "http://localhost:8000/docs"
    }
)

# CORS: allow-list configurable via the CORS_ORIGINS env var (comma-separated).
_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a persistent temp directory for uploads within the project
TEMP_UPLOAD_DIR = Path(__file__).parent / "tempfolder"
TEMP_UPLOAD_DIR.mkdir(exist_ok=True)
TEMP_UPLOAD_DIR_RESOLVED = TEMP_UPLOAD_DIR.resolve()

# Supported file extensions (ordered tuple for stable messages)
SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.doc')
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


@app.get(
    "/",
    response_model=RootResponse,
    tags=["Info"],
    summary="API Root Information",
    responses={
        200: {
            "description": "API information and available endpoints",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Document to Markdown Converter API",
                        "status": "running",
                        "endpoints": {
                            "POST /convert": "Upload document and convert to markdown",
                            "GET /health": "Health check",
                            "GET /files": "List all converted files",
                            "DELETE /cleanup": "Delete all temporary files",
"POST /extract": "Extract contract fields from a markdown file",
                        "GET /extractions": "List all stored extractions",
                        "GET /extractions/{id}": "Get a stored extraction by ID",
"POST /assess-risk": "Assess contract risks against the rulebook",
"GET /extractions/{extraction_id}/risks": "List risks assessed for an extraction",
            "PATCH /risks/{risk_id}": "Review a contract risk (approve, reject, or edit while pending)",
            "GET /extractions/{extraction_id}/summary-email": "Generate a summary email body for an extraction"
                    }
                    }
                }
            }
        }
    }
)
async def root():
    """
    Get API information and available endpoints.

    **Sample Response:**
    ```json
    {
      "message": "Document to Markdown Converter API",
      "status": "running",
      "endpoints": {
        "POST /convert": "Upload document and convert to markdown",
        "GET /health": "Health check",
        "GET /files": "List all converted files",
        "DELETE /cleanup": "Delete all temporary files",
        "POST /extract": "Extract contract fields from a markdown file",
        "GET /extractions": "List all stored extractions",
        "GET /extractions/{id}": "Get a stored extraction by ID"
      }
    }
    ```
    """
    return RootResponse(
        message="Document to Markdown Converter API",
        status="running",
        endpoints={
            "POST /convert": "Upload document and convert to markdown",
            "GET /health": "Health check",
            "GET /files": "List all converted files",
            "DELETE /cleanup": "Delete all temporary files",
            "POST /extract": "Extract contract fields from a markdown file",
            "GET /extractions": "List all stored extractions",
            "GET /extractions/{id}": "Get a stored extraction by ID",
            "POST /assess-risk": "Assess contract risks against the rulebook",
            "GET /extractions/{extraction_id}/risks": "List risks assessed for an extraction",
            "PATCH /risks/{risk_id}": "Review a contract risk (approve, reject, or edit while pending)",
            "GET /extractions/{extraction_id}/summary-email": "Generate a summary email body for an extraction"
        }
    )


@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["Health"],
    summary="API Health Check",
    responses={
        200: {
            "description": "API is healthy and running",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "temp_dir": "/Users/mac/Downloads/contractiq/tempfolder"
                    }
                }
            }
        }
    }
)
async def health_check():
    """
    Check if the API is healthy and running.

    **Use this endpoint to:**
    - Verify API connectivity
    - Check temporary directory location
    - Monitor API availability

    **Sample Response:**
    ```json
    {
      "status": "healthy",
      "temp_dir": "/Users/mac/Downloads/contractiq/tempfolder"
    }
    ```

    **Response Fields:**
    - `status`: Current API status (should be "healthy")
    - `temp_dir`: Path to the temporary folder where files are stored
    """
    return HealthCheckResponse(
        status="healthy",
        temp_dir=str(TEMP_UPLOAD_DIR)
    )


@app.post(
    "/convert",
    response_model=ConvertSuccessResponse,
    tags=["Conversion"],
    summary="Upload and Convert Document to Markdown",
    responses={
        200: {
            "description": "Document successfully converted to Markdown",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Document converted successfully",
                        "original_file": "contract.pdf",
                        "original_file_path": "/Users/mac/Downloads/contractiq/tempfolder/contract/contract.pdf",
                        "original_file_size_bytes": 154230,
                        "markdown_filename": "contract_extracted.md",
                        "markdown_file_path": "/Users/mac/Downloads/contractiq/tempfolder/contract/contract_extracted.md",
                        "markdown_file_size_bytes": 6919,
                        "file_folder": "/Users/mac/Downloads/contractiq/tempfolder/contract",
                        "folder_name": "contract",
                        "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder",
                        "conversion_status": "completed"
                    }
                }
            }
        },
        400: {
            "description": "Bad request - unsupported file format or empty document",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Unsupported file format: .txt. Supported formats: .pdf, .docx, .doc"
                    }
                }
            }
        },
        413: {
            "description": "Payload too large",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "File too large. Maximum size: 50.0MB"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error during conversion",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error converting document: Tesseract is not installed"
                    }
                }
            }
        }
    }
)
async def convert_document(file: UploadFile = File(..., description="Document file to convert (PDF, DOCX, or DOC)")):
    """
    Upload a document and convert it to Markdown format.

    **Supported File Formats:**
    - `.pdf` - PDF documents (text-based and scanned)
    - `.docx` - Microsoft Word (2007+)
    - `.doc` - Microsoft Word (97-2003)

    **Features:**
    - Automatic OCR for scanned PDFs
    - Preserves document structure
    - Creates organized folder structure
    - Stores both original and converted files

    **Request:**
    - Content-Type: multipart/form-data
    - File parameter: Your document file (max 50 MB)

    **cURL Example:**
    ```bash
    curl -X POST "http://localhost:8000/convert" \\
      -F "file=@contract.pdf"
    ```

    **Python Example:**
    ```python
    import requests

    files = {'file': open('contract.pdf', 'rb')}
    response = requests.post('http://localhost:8000/convert', files=files)
    result = response.json()
    print(f"Markdown: {result['markdown_file_path']}")
    ```

    **JavaScript Example:**
    ```javascript
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    fetch('http://localhost:8000/convert', {
      method: 'POST',
      body: formData
    })
    .then(r => r.json())
    .then(data => console.log(data.markdown_file_path));
    ```

    **Response Fields:**
    - `success`: Boolean indicating successful conversion
    - `original_file`: Name of uploaded file
    - `original_file_path`: Full path to stored original file
    - `original_file_size_bytes`: Size of original file in bytes
    - `markdown_filename`: Generated markdown filename
    - `markdown_file_path`: Full path to generated markdown file
    - `markdown_file_size_bytes`: Size of markdown file in bytes
    - `file_folder`: Dedicated folder containing both files
    - `folder_name`: Name of the created folder
    - `temp_directory`: Path to temporary storage directory
    - `conversion_status`: Status of conversion (completed)

    **Sample Response:**
    ```json
    {
      "success": true,
      "message": "Document converted successfully",
      "original_file": "contract.pdf",
      "original_file_path": "/Users/mac/Downloads/contractiq/tempfolder/contract/contract.pdf",
      "original_file_size_bytes": 154230,
      "markdown_filename": "contract_extracted.md",
      "markdown_file_path": "/Users/mac/Downloads/contractiq/tempfolder/contract/contract_extracted.md",
      "markdown_file_size_bytes": 6919,
      "file_folder": "/Users/mac/Downloads/contractiq/tempfolder/contract",
      "folder_name": "contract",
      "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder",
      "conversion_status": "completed"
    }
    ```
    """

    temp_input_path = None
    temp_output_path = None
    file_folder = None
    success = False

    try:
        # Sanitize the client-supplied filename: strip any directory components
        # so a value like "../../evil.pdf" cannot escape the temp directory.
        safe_filename = Path(file.filename).name if file.filename else ""
        if not safe_filename or safe_filename in {".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid file name.")

        file_extension = Path(safe_filename).suffix.lower()
        if file_extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_extension}. "
                       f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"
            )

        # Create a dedicated folder for this document (confined to temp dir)
        original_filename = Path(safe_filename).stem
        file_folder = (TEMP_UPLOAD_DIR / original_filename).resolve()
        temp_input_path = (file_folder / safe_filename).resolve()

        if not file_folder.is_relative_to(TEMP_UPLOAD_DIR_RESOLVED) or \
                not temp_input_path.is_relative_to(TEMP_UPLOAD_DIR_RESOLVED):
            raise HTTPException(status_code=400, detail="Invalid file name.")

        file_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created folder: {file_folder}")

        # Stream the upload to disk, enforcing the size limit as we go.
        total_bytes = 0
        with open(temp_input_path, 'wb') as f:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024*1024)}MB"
                    )
                f.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=400,
                detail="Document appears to be empty or could not be read."
            )

        logger.info(f"File uploaded to folder: {safe_filename} ({total_bytes} bytes)")

        # Convert document to markdown
        logger.info(f"Converting {safe_filename} to markdown...")
        markdown_content = DocumentConverter.convert_document(
            str(temp_input_path),
            file_extension
        )

        if not markdown_content.strip():
            raise HTTPException(
                status_code=400,
                detail="Document appears to be empty or could not be read."
            )

        # Save markdown file in the same folder
        markdown_filename = f"{original_filename}_extracted.md"
        temp_output_path = file_folder / markdown_filename

        with open(temp_output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        markdown_file_size = os.path.getsize(temp_output_path)
        original_file_size = os.path.getsize(temp_input_path)
        logger.info(f"Markdown file created: {markdown_filename} ({markdown_file_size} bytes)")

        success = True
        return ConvertSuccessResponse(
            success=True,
            message="Document converted successfully",
            original_file=safe_filename,
            original_file_path=str(temp_input_path),
            original_file_size_bytes=original_file_size,
            markdown_filename=markdown_filename,
            markdown_file_path=str(temp_output_path),
            markdown_file_size_bytes=markdown_file_size,
            file_folder=str(file_folder),
            folder_name=original_filename,
            temp_directory=str(TEMP_UPLOAD_DIR),
            conversion_status="completed"
        )

    except HTTPException as e:
        logger.error(f"Validation error: {e.detail}")
        raise e

    except DocumentConversionError as e:
        logger.error(f"Conversion failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Could not convert document: {str(e)}"
        )

    except ConversionServiceError as e:
        logger.error(f"Conversion service error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error converting document: {str(e)}"
        )

    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error converting document. Please check server logs."
        )

    finally:
        # Do not leave partial/broken folders behind on failure.
        if not success and file_folder is not None and file_folder.exists():
            try:
                shutil.rmtree(file_folder)
            except OSError:
                logger.warning(f"Could not clean up failed conversion folder: {file_folder}")


@app.get(
    "/files",
    response_model=ListFilesResponse,
    tags=["Files"],
    summary="List All Converted Documents",
    responses={
        200: {
            "description": "Successfully retrieved list of all converted documents",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "total_folders": 2,
                        "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder",
                        "folders": [
                            {
                                "folder_name": "contract",
                                "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/contract",
                                "original_file": "contract.pdf",
                                "original_file_size_bytes": 154230,
                                "markdown_file": "contract_extracted.md",
                                "markdown_file_size_bytes": 6919,
                                "total_files": 2,
                                "created": 1694529201.0
                            },
                            {
                                "folder_name": "invoice",
                                "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/invoice",
                                "original_file": "invoice.docx",
                                "original_file_size_bytes": 45600,
                                "markdown_file": "invoice_extracted.md",
                                "markdown_file_size_bytes": 3200,
                                "total_files": 2,
                                "created": 1694529250.0
                            }
                        ]
                    }
                }
            }
        },
        500: {
            "description": "Error listing files",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error listing files: Permission denied"
                    }
                }
            }
        }
    }
)
async def list_converted_files():
    """
    List all converted documents and their associated files.

    **Use this endpoint to:**
    - Browse all converted documents
    - Check file sizes and paths
    - Track conversion history
    - Verify document processing

    **cURL Example:**
    ```bash
    curl http://localhost:8000/files | jq '.'
    ```

    **Python Example:**
    ```python
    import requests

    response = requests.get('http://localhost:8000/files')
    files = response.json()

    for folder in files['folders']:
        print(f"Folder: {folder['folder_name']}")
        print(f"  Original: {folder['original_file']} ({folder['original_file_size_bytes']} bytes)")
        print(f"  Markdown: {folder['markdown_file']} ({folder['markdown_file_size_bytes']} bytes)")
    ```

    **Response Fields:**
    - `success`: Boolean indicating successful retrieval
    - `total_folders`: Number of document folders
    - `temp_directory`: Path to temporary storage directory
    - `folders`: Array of folder information objects
      - `folder_name`: Name of the document folder
      - `folder_path`: Full path to the folder
      - `original_file`: Name of original uploaded file
      - `original_file_size_bytes`: Size of original file
      - `markdown_file`: Name of converted markdown file
      - `markdown_file_size_bytes`: Size of markdown file
      - `total_files`: Number of files in folder (usually 2)
      - `created`: Timestamp when folder was created

    **Sample Response:**
    ```json
    {
      "success": true,
      "total_folders": 2,
      "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder",
      "folders": [
        {
          "folder_name": "contract",
          "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/contract",
          "original_file": "contract.pdf",
          "original_file_size_bytes": 154230,
          "markdown_file": "contract_extracted.md",
          "markdown_file_size_bytes": 6919,
          "total_files": 2,
          "created": 1694529201.0
        }
      ]
    }
    ```
    """
    try:
        folders_info = []

        # Iterate through all folders in TEMP_UPLOAD_DIR
        for folder in TEMP_UPLOAD_DIR.iterdir():
            if folder.is_dir():
                original_file = None
                markdown_file = None
                original_file_size = 0
                markdown_file_size = 0

                # Find original file and markdown file in folder
                for file in folder.iterdir():
                    if file.is_file():
                        if file.name.endswith('_extracted.md'):
                            markdown_file = file.name
                            markdown_file_size = os.path.getsize(file)
                        else:
                            original_file = file.name
                            original_file_size = os.path.getsize(file)

                folders_info.append(FileInfo(
                    folder_name=folder.name,
                    folder_path=str(folder),
                    original_file=original_file,
                    original_file_size_bytes=original_file_size if original_file else 0,
                    markdown_file=markdown_file,
                    markdown_file_size_bytes=markdown_file_size if markdown_file else 0,
                    total_files=len(list(folder.iterdir())),
                    created=os.path.getctime(folder)
                ))

        return ListFilesResponse(
            success=True,
            total_folders=len(folders_info),
            temp_directory=str(TEMP_UPLOAD_DIR),
            folders=folders_info
        )

    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error listing files. Please check server logs."
        )


@app.delete(
    "/cleanup",
    response_model=CleanupResponse,
    tags=["Files"],
    summary="Delete All Converted Documents",
    responses={
        200: {
            "description": "Successfully cleaned up all temporary files",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Cleaned up 5 items",
                        "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder"
                    }
                }
            }
        },
        500: {
            "description": "Error during cleanup",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error cleaning up files: Permission denied"
                    }
                }
            }
        }
    }
)
async def cleanup_temp_files():
    """
    Delete all converted documents and their folders from temporary storage.

    ⚠️ **WARNING:** This action is irreversible! All documents will be permanently deleted.

    **Use this endpoint to:**
    - Free up disk space
    - Clear old conversions
    - Reset the temporary storage

    **cURL Example:**
    ```bash
    curl -X DELETE http://localhost:8000/cleanup
    ```

    **Python Example:**
    ```python
    import requests

    response = requests.delete('http://localhost:8000/cleanup')
    result = response.json()
    print(f"Cleaned up {result['message']}")
    ```

    **Response Fields:**
    - `success`: Boolean indicating successful cleanup
    - `message`: Description of cleanup result
    - `temp_directory`: Path to temporary storage directory

    **Sample Response:**
    ```json
    {
      "success": true,
      "message": "Cleaned up 5 items",
      "temp_directory": "/Users/mac/Downloads/contractiq/tempfolder"
    }
    ```
    """
    try:
        deleted_count = 0
        for item in TEMP_UPLOAD_DIR.glob("*"):
            if item.is_file():
                os.remove(item)
                deleted_count += 1
            elif item.is_dir():
                # Remove directory and all contents
                shutil.rmtree(item)
                deleted_count += 1

        return CleanupResponse(
            success=True,
            message=f"Cleaned up {deleted_count} items",
            temp_directory=str(TEMP_UPLOAD_DIR)
        )

    except Exception as e:
        logger.error(f"Error cleaning up files: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error cleaning up files. Please check server logs."
        )


# ==================== Contract Extraction Endpoints ====================

@app.post(
    "/extract",
    response_model=ExtractedFieldsResponse,
    tags=["Extraction"],
    summary="Extract Contract Fields",
    responses={
        200: {
            "description": "Contract fields extracted and stored successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Contract fields extracted successfully",
                        "extraction_id": 1,
                        "extracted_fields": {
                            "id": 1,
                            "markdown_filename": "contract_extracted.md",
                            "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/contract",
                            "extraction_timestamp": "2026-09-12T19:30:00",
                            "subject_to_lease": "Yes — tenanted",
                            "date_of_tenancy": "2026-11-14",
                            "contract_price": 1285000,
                            "deposit_amount": 128500,
                            "deposit_due_date": "2026-09-13",
                            "subject_to_finance": True,
                            "settlement_date": "30 days from signing",
                            "gst_clause": "Price is GST inclusive",
                            "terms_contract": "Standard terms apply",
                            "default_provisions": "Interest 12% p.a. on default",
                            "due_date_extension": None,
                            "special_conditions": "14 identified — 3 affect purchaser"
                        },
                        "extracted_parameters": [
                            {
                                "parameter_name": "subject_to_lease",
                                "parameter_value": "Yes — tenanted",
                                "confidence_score": 95,
                                "reference": {
                                    "page_num": 1,
                                    "section_number": "2.1",
                                    "section_title": "Property Details"
                                }
                            },
                            {
                                "parameter_name": "contract_price",
                                "parameter_value": "1285000",
                                "confidence_score": 98,
                                "reference": {
                                    "page_num": 2,
                                    "section_number": "3.2",
                                    "section_title": "Purchase Price"
                                }
                            }
                        ],
                        "timestamp": "2026-09-12T19:30:00"
                    }
                }
            }
        },
        400: {
            "description": "Bad request - invalid file path or file not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "File not found: /path/to/nonexistent/file.md"
                    }
                }
            }
        },
        500: {
            "description": "Internal server error during extraction",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error extracting contract fields: API error or validation failed"
                    }
                }
            }
        }
    }
)
async def extract_contract_fields(
    request: ExtractRequest,
    session: Session = Depends(get_session)
):
    """
    Extract 12 predefined fields from a contract Markdown file using LLM.

    **Extracted Fields:**
    1. subject_to_lease - Whether property is subject to lease/tenancy
    2. date_of_tenancy - Date tenancy begins
    3. contract_price - Agreed purchase price
    4. deposit_amount - Required deposit
    5. deposit_due_date - Deposit payment due date
    6. subject_to_finance - Finance approval condition
    7. settlement_date - Settlement/completion date
    8. gst_clause - GST clause details
    9. terms_contract - Key contractual terms
    10. default_provisions - Default/breach provisions
    11. due_date_extension - Extension provisions
    12. special_conditions - Special/unique clauses

    **Request:**
    ```json
    {
      "markdown_file_path": "/Users/mac/Downloads/contractiq/tempfolder/contract/contract_extracted.md"
    }
    ```

    **cURL Example:**
    ```bash
    curl -X POST "http://localhost:8000/extract" \\
      -H "Content-Type: application/json" \\
      -d '{"markdown_file_path": "/path/to/contract_extracted.md"}'
    ```

    **Python Example:**
    ```python
    import requests

    response = requests.post(
        'http://localhost:8000/extract',
        json={"markdown_file_path": "/path/to/contract.md"}
    )
    result = response.json()
    print(f"Extraction ID: {result['extraction_id']}")
    print(f"Fields: {result['extracted_fields']}")
    ```

    **Response Fields:**
    - `success`: Boolean indicating successful extraction
    - `message`: Status message
    - `extraction_id`: Database record ID of extraction
    - `extracted_fields`: All 12 extracted contract fields
    - `timestamp`: When extraction was performed
    """
    try:
        # Confine the requested path to the temporary directory.
        try:
            requested_path = Path(request.markdown_file_path).resolve()
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid markdown_file_path.")

        if not requested_path.is_relative_to(TEMP_UPLOAD_DIR_RESOLVED):
            raise HTTPException(
                status_code=400,
                detail="markdown_file_path must point to a file inside the temporary directory."
            )

        # Get the extractor
        extractor = get_extractor()

        # Extract fields from markdown file
        logger.info(f"Extracting fields from: {requested_path}")
        extracted_data = extractor.extract_from_file(
            str(requested_path), base_dir=str(TEMP_UPLOAD_DIR_RESOLVED)
        )

        # Get markdown filename from path
        markdown_filename = requested_path.name
        folder_path = str(requested_path.parent)

        # Create database record
        timestamp = datetime.now().isoformat()

        # Convert extracted_parameters to JSON for storage
        extracted_params_json = None
        extracted_params_list = None
        if extracted_data.extracted_parameters:
            extracted_params_list = extracted_data.extracted_parameters
            extracted_params_json = json.dumps(
                [param.model_dump() for param in extracted_data.extracted_parameters],
                indent=2
            )

        db_record = ContractExtract(
            subject_to_lease=extracted_data.subject_to_lease,
            date_of_tenancy=extracted_data.date_of_tenancy,
            contract_price=extracted_data.contract_price,
            deposit_amount=extracted_data.deposit_amount,
            deposit_due_date=extracted_data.deposit_due_date,
            subject_to_finance=extracted_data.subject_to_finance,
            settlement_date=extracted_data.settlement_date,
            gst_clause=extracted_data.gst_clause,
            terms_contract=extracted_data.terms_contract,
            default_provisions=extracted_data.default_provisions,
            due_date_extension=extracted_data.due_date_extension,
            special_conditions=extracted_data.special_conditions,
            markdown_filename=markdown_filename,
            folder_path=folder_path,
            extraction_timestamp=timestamp,
            extracted_parameters=extracted_params_json
        )

        # Save to database
        session.add(db_record)
        session.commit()
        session.refresh(db_record)

        logger.info(f"Extraction saved to database with ID: {db_record.id}")

        return ExtractedFieldsResponse(
            success=True,
            message="Contract fields extracted successfully",
            extraction_id=db_record.id,
            extracted_fields=ContractExtractResponse.model_validate(db_record, from_attributes=True),
            extracted_parameters=extracted_params_list,
            timestamp=timestamp
        )

    except HTTPException:
        raise

    except FileNotFoundError as e:
        logger.error(f"File not found: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except InvalidMarkdownFileError as e:
        logger.error(f"Invalid markdown file: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except MissingApiKeyError as e:
        logger.error(f"Missing API key: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Extraction service is not configured (missing OPENAI_API_KEY)."
        )

    except ContractExtractionError as e:
        logger.error(f"Extraction error: {str(e)}")
        raise HTTPException(status_code=500, detail="Extraction failed. Please check server logs.")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error extracting contract. Please check server logs."
        )


@app.get(
    "/extractions",
    response_model=ExtractionListResponse,
    tags=["Extraction"],
    summary="List All Extracted Contracts",
    responses={
        200: {
            "description": "Successfully retrieved list of extractions",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "total_extractions": 2,
                        "extractions": [
                            {
                                "id": 1,
                                "markdown_filename": "contract_extracted.md",
                                "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/contract",
                                "extraction_timestamp": "2026-09-12T19:30:00",
                                "subject_to_lease": "Yes — tenanted",
                                "contract_price": 1285000
                            }
                        ]
                    }
                }
            }
        },
        500: {
            "description": "Error retrieving extractions",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Error retrieving extractions: Database error"
                    }
                }
            }
        }
    }
)
async def list_extractions(session: Session = Depends(get_session)):
    """
    List all extracted contracts from the database.

    **Use this endpoint to:**
    - View extraction history
    - Find previously extracted contracts
    - Verify extraction results
    - Access extracted data

    **cURL Example:**
    ```bash
    curl http://localhost:8000/extractions
    ```

    **Response includes:**
    - All 12 extracted contract fields for each extraction
    - Database record ID
    - Original markdown filename
    - Extraction timestamp

    **Sample Response:**
    ```json
    {
      "success": true,
      "total_extractions": 2,
      "extractions": [
        {
          "id": 1,
          "markdown_filename": "contract_extracted.md",
          "folder_path": "/Users/mac/Downloads/contractiq/tempfolder/contract",
          "extraction_timestamp": "2026-09-12T19:30:00",
          "subject_to_lease": "Yes — tenanted",
          "date_of_tenancy": "2026-11-14",
          "contract_price": 1285000,
          "deposit_amount": 128500,
          ...
        }
      ]
    }
    ```
    """
    try:
        # Query all extractions
        statement = select(ContractExtract).order_by(ContractExtract.id.desc())
        extractions = session.exec(statement).all()

        logger.info(f"Retrieved {len(extractions)} extractions from database")

        return ExtractionListResponse(
            success=True,
            total_extractions=len(extractions),
            extractions=[ContractExtractResponse.model_validate(e, from_attributes=True) for e in extractions]
        )

    except Exception as e:
        logger.error(f"Error retrieving extractions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving extractions. Please check server logs."
        )


@app.get(
    "/extractions/{extraction_id}",
    response_model=ContractExtractResponse,
    tags=["Extraction"],
    summary="Get Extraction by ID",
    responses={
        200: {
            "description": "Successfully retrieved extraction",
        },
        404: {
            "description": "Extraction not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Extraction not found with ID: 999"
                    }
                }
            }
        }
    }
)
async def get_extraction(extraction_id: int, session: Session = Depends(get_session)):
    """
    Get a specific extraction by ID.

    **Parameters:**
    - `extraction_id`: The database ID of the extraction

    **cURL Example:**
    ```bash
    curl http://localhost:8000/extractions/1
    ```

    **Response:**
    Returns the complete extraction record with all 12 extracted fields.
    """
    try:
        extraction = session.get(ContractExtract, extraction_id)

        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction not found with ID: {extraction_id}"
            )

        logger.info(f"Retrieved extraction {extraction_id}")
        return ContractExtractResponse.model_validate(extraction, from_attributes=True)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error retrieving extraction: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving extraction. Please check server logs."
        )


# ==================== Risk Assessment Endpoints ====================

ASSESS_FIELD_COLUMNS = [
    "subject_to_lease", "date_of_tenancy", "contract_price", "deposit_amount",
    "deposit_due_date", "subject_to_finance", "settlement_date", "gst_clause",
    "terms_contract", "default_provisions", "due_date_extension", "special_conditions",
]


def _build_extracted_fields(extraction) -> dict:
    """Rebuild the 12-field extracted_fields dict from a ContractExtract row."""
    fields = {}
    for column in ASSESS_FIELD_COLUMNS:
        value = getattr(extraction, column)
        if isinstance(value, str):
            try:
                fields[column] = json.loads(value)
            except json.JSONDecodeError:
                fields[column] = value
        else:
            fields[column] = value
    return fields


def _jurisdiction_from_extraction(extraction) -> Optional[str]:
    """Derive a jurisdiction from stored extraction data, if any exists."""
    if not extraction.extracted_parameters:
        return None
    try:
        params = json.loads(extraction.extracted_parameters)
    except (json.JSONDecodeError, TypeError):
        return None
    for param in params or []:
        key = str(param.get("parameter_name", "")).lower().strip()
        if key in ("state", "property_state", "jurisdiction"):
            value = str(param.get("parameter_value", "")).strip().upper()
            if value in ("VIC", "NSW"):
                return value
    return None


@app.post(
    "/assess-risk",
    response_model=AssessRiskResponse,
    tags=["Risk Assessment"],
    summary="Assess Contract Risks Against the Rulebook",
    responses={
        200: {
            "description": "Risk assessment completed and risks saved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Risk assessment completed",
                        "extraction_id": 1,
                        "jurisdiction": "VIC",
                        "total_risks": 32,
                        "timestamp": "2026-09-18T10:00:00"
                    }
                }
            }
        },
        400: {
            "description": "Invalid jurisdiction override",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "jurisdiction must be 'VIC', 'NSW', or omitted."
                    }
                }
            }
        },
        404: {
            "description": "Extraction not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Extraction not found with ID: 999"
                    }
                }
            }
        },
        409: {
            "description": "Risk assessment already reviewed; re-run blocked",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Risk assessment already reviewed for extraction 1"
                    }
                }
            }
        },
        500: {
            "description": "Risk assessment service failure",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Risk assessment failed. Please check server logs."
                    }
                }
            }
        }
    }
)
async def assess_contract_risks(
    request: AssessRiskRequest,
    session: Session = Depends(get_session)
):
    """
    Assess an existing extraction against the rulebook and save the risks.

    **Request:**
    ```json
    {
        "extraction_id": 1,
        "jurisdiction": "VIC"
    }
    ```

    **Behavior:**
    - Looks up the extraction by ID (404 if missing).
    - Resolves the jurisdiction from the request override, otherwise from the
      extraction's stored fields, otherwise None (full rulebook).
    - Re-runs freely when no risks exist or all are still "pending"; returns
      409 if any existing risk has been reviewed (approved/rejected), to
      protect reviewer work.
    - Saves one ContractRisk row per rule and one AuditLog "created" entry
      per risk. Never deletes audit entries.

    **cURL Example:**
    ```bash
    curl -X POST "http://localhost:8000/assess-risk" \\
      -H "Content-Type: application/json" \\
      -d '{"extraction_id": 1, "jurisdiction": "VIC"}'
    ```
    """
    try:
        extraction = session.get(ContractExtract, request.extraction_id)
        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction not found with ID: {request.extraction_id}"
            )

        jurisdiction = request.jurisdiction
        if jurisdiction is not None and jurisdiction not in ("VIC", "NSW"):
            raise HTTPException(
                status_code=400,
                detail="jurisdiction must be 'VIC', 'NSW', or omitted."
            )
        if jurisdiction is None:
            jurisdiction = _jurisdiction_from_extraction(extraction)

        existing_risks = session.exec(
            select(ContractRisk).where(ContractRisk.extraction_id == extraction.id)
        ).all()
        if existing_risks:
            reviewed = [r for r in existing_risks if r.reviewer_status != "pending"]
            if reviewed:
                reviewed_states = ", ".join(sorted({r.reviewer_status for r in reviewed}))
                raise HTTPException(
                    status_code=409,
                    detail=f"Risk assessment already reviewed for extraction "
                           f"{extraction.id} ({len(reviewed)} risk(s) no longer "
                           f"pending: {reviewed_states}); re-run is blocked to "
                           f"protect reviewer work."
                )
            for risk in existing_risks:
                session.delete(risk)
            session.commit()
            logger.info(
                f"Re-running assessment for extraction {extraction.id}: "
                f"removed {len(existing_risks)} untouched risk rows"
            )

        extracted_fields = _build_extracted_fields(extraction)
        risks = assess_risks(extracted_fields, jurisdiction=jurisdiction)

        timestamp = datetime.now().isoformat()
        risk_rows = []
        for item in risks:
            risk_rows.append(ContractRisk(
                extraction_id=extraction.id,
                rule_id=item.rule_id,
                risk_short_desc=item.risk_short_desc,
                risk_long_desc=item.risk_long_desc,
                confidence_score=item.confidence_score,
                reference=item.reference.model_dump_json() if item.reference else None,
                assessment_status=item.assessment_status,
                reviewer_status="pending",
                was_edited=False,
            ))
        session.add_all(risk_rows)
        session.commit()

        for risk in risk_rows:
            session.add(AuditLog(
                contract_risk_id=risk.id,
                action="created",
                ai_value=json.dumps(risk.risk_short_desc),
                human_value=None,
                changed_by=None,
            ))
        session.commit()

        logger.info(
            f"Saved {len(risk_rows)} risks for extraction {extraction.id} "
            f"(jurisdiction={jurisdiction})"
        )

        return AssessRiskResponse(
            success=True,
            message="Risk assessment completed",
            extraction_id=extraction.id,
            jurisdiction=jurisdiction,
            risks=risks,
            total_risks=len(risks),
            timestamp=timestamp,
        )

    except HTTPException:
        raise

    except MissingApiKeyError as e:
        logger.error(f"Missing API key: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Risk assessment service is not configured (missing OPENAI_API_KEY)."
        )

    except RiskAssessmentError as e:
        logger.error(f"Risk assessment error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Risk assessment failed. Please check server logs."
        )

    except Exception as e:
        logger.error(f"Unexpected risk assessment error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error assessing risks. Please check server logs."
        )


def _risk_item_from_row(row: ContractRisk) -> RiskItem:
    """Deserialize a ContractRisk row back into a RiskItem response shape.

    Mirrors the reference deserialization pattern used in
    services.contract_extractor._validate_and_normalize: json.loads the stored
    JSON string, then build a Reference from the dict, defaulting to empty on
    any parse failure.
    """
    reference = Reference()
    if row.reference:
        try:
            ref_data = json.loads(row.reference)
            if isinstance(ref_data, dict):
                reference = Reference(
                    page_num=ref_data.get("page_num"),
                    section_number=ref_data.get("section_number"),
                    section_title=ref_data.get("section_title"),
                )
        except (json.JSONDecodeError, TypeError):
            reference = Reference()

    return RiskItem(
        rule_id=row.rule_id,
        risk_short_desc=row.risk_short_desc,
        risk_long_desc=row.risk_long_desc,
        confidence_score=row.confidence_score,
        reference=reference,
        assessment_status=row.assessment_status,
        reviewer_status=row.reviewer_status,
        was_edited=row.was_edited,
    )


@app.get(
    "/extractions/{extraction_id}/risks",
    response_model=RiskListResponse,
    tags=["Risk Assessment"],
    summary="List Risks for an Extraction",
    responses={
        200: {
            "description": "Stored risks for the extraction (may be an empty list)",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "extraction_id": 1,
                        "total_risks": 32,
                        "risks": [
                            {
                                "rule_id": "VIC-DISC-001",
                                "risk_short_desc": "Section 32 evidence missing",
                                "risk_long_desc": "Request the Section 32 statement before proceeding.",
                                "confidence_score": 92,
                                "reference": {
                                    "page_num": 2,
                                    "section_number": "3.2",
                                    "section_title": "Disclosure",
                                },
                                "assessment_status": "Found",
                                "reviewer_status": "pending",
                                "was_edited": False,
                            }
                        ],
                    }
                }
            }
        },
        404: {
            "description": "Extraction not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Extraction not found with ID: 999"
                    }
                }
            }
        }
    }
)
async def get_extraction_risks(
    extraction_id: int,
    session: Session = Depends(get_session)
):
    """
    List the stored risk assessment results for an extraction.

    Returns risks in insertion (id) order. If the extraction exists but no
    assessment has been run yet, returns an empty list with HTTP 200 — a 404
    is only returned when the extraction_id itself does not exist.

    **cURL Example:**
    ```bash
    curl http://localhost:8000/extractions/1/risks
    ```

    **Response:**
    Returns all stored ContractRisk rows for the extraction, with each row's
    reference JSON deserialized back into the Reference shape.
    """
    try:
        extraction = session.get(ContractExtract, extraction_id)

        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction not found with ID: {extraction_id}"
            )

        risks = session.exec(
            select(ContractRisk)
            .where(ContractRisk.extraction_id == extraction_id)
            .order_by(ContractRisk.id)
        ).all()

        risk_items = [_risk_item_from_row(row) for row in risks]
        logger.info(f"Listed {len(risk_items)} risks for extraction {extraction_id}")
        return RiskListResponse(
            success=True,
            extraction_id=extraction_id,
            total_risks=len(risk_items),
            risks=risk_items,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error retrieving risks: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving risks. Please check server logs."
        )


@app.patch(
    "/risks/{risk_id}",
    response_model=RiskItem,
    tags=["Risk Assessment"],
    summary="Review a Contract Risk (Approve, Reject, or Edit)",
    responses={
        200: {
            "description": "The updated risk item",
            "content": {
                "application/json": {
                    "example": {
                        "rule_id": "VIC-DISC-001",
                        "risk_short_desc": "Section 32 statement requested from vendor",
                        "risk_long_desc": "Vendor to provide the Section 32 statement before exchange.",
                        "confidence_score": 92,
                        "reference": {
                            "page_num": 2,
                            "section_number": "3.2",
                            "section_title": "Disclosure",
                        },
                        "assessment_status": "Found",
                        "reviewer_status": "approved",
                        "was_edited": False,
                    }
                }
            }
        },
        400: {
            "description": "Invalid review request",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "action 'edit' requires at least one of risk_short_desc or risk_long_desc"
                    }
                }
            }
        },
        404: {
            "description": "Risk not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Risk not found with ID: 999"
                    }
                }
            }
        },
        409: {
            "description": "Risk already reviewed; no longer pending",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Risk 12 has already been reviewed (approved); only pending risks can be reviewed"
                    }
                }
            }
        }
    }
)
async def review_contract_risk(
    risk_id: int,
    request: RiskUpdateRequest,
    session: Session = Depends(get_session)
):
    """
    Review a single contract risk: approve, reject, or edit it.

    All actions require the risk to still be in `pending` review status.
    Approve/reject set the reviewer_status; edit updates the text fields and
    sets was_edited=True WITHOUT changing reviewer_status. Every change is
    recorded as an append-only AuditLog entry with the reviewer's identity.

    **cURL Example:**
    ```bash
    curl -X PATCH "http://localhost:8000/risks/12" \\
      -H "Content-Type: application/json" \\
      -d '{"action": "edit", "changed_by": "ashraf@example.com",
           "risk_short_desc": "Section 32 statement requested from vendor"}'
    ```
    """
    try:
        if not request.changed_by.strip():
            raise HTTPException(
                status_code=400,
                detail="changed_by is required and must be a non-empty string"
            )

        risk = session.get(ContractRisk, risk_id)
        if not risk:
            raise HTTPException(
                status_code=404,
                detail=f"Risk not found with ID: {risk_id}"
            )

        if risk.reviewer_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Risk {risk_id} has already been reviewed "
                       f"({risk.reviewer_status}); only pending risks can be reviewed"
            )

        if request.action == RiskReviewAction.approve:
            risk.reviewer_status = "approved"
            session.add(AuditLog(
                contract_risk_id=risk.id,
                action="approved",
                changed_by=request.changed_by,
            ))
        elif request.action == RiskReviewAction.reject:
            risk.reviewer_status = "rejected"
            session.add(AuditLog(
                contract_risk_id=risk.id,
                action="rejected",
                changed_by=request.changed_by,
            ))
        elif request.action == RiskReviewAction.edit:
            fields_to_edit = {
                "risk_short_desc": request.risk_short_desc,
                "risk_long_desc": request.risk_long_desc,
            }
            supplied = {
                name: new_value
                for name, new_value in fields_to_edit.items()
                if new_value is not None
            }
            if not supplied:
                raise HTTPException(
                    status_code=400,
                    detail="action 'edit' requires at least one of "
                           "risk_short_desc or risk_long_desc"
                )

            for field_name, new_value in supplied.items():
                old_value = getattr(risk, field_name)
                if new_value == old_value:
                    continue
                setattr(risk, field_name, new_value)
                risk.was_edited = True
                session.add(AuditLog(
                    contract_risk_id=risk.id,
                    action="edited",
                    field_changed=field_name,
                    ai_value=json.dumps(old_value) if old_value is not None else None,
                    human_value=json.dumps(new_value),
                    changed_by=request.changed_by,
                ))

        session.commit()
        session.refresh(risk)
        logger.info(
            f"Risk {risk.id} {request.action.value} by {request.changed_by} "
            f"(status={risk.reviewer_status}, was_edited={risk.was_edited})"
        )
        return _risk_item_from_row(risk)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error reviewing risk: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error reviewing risk. Please check server logs."
        )


@app.get(
    "/extractions/{extraction_id}/summary-email",
    response_model=SummaryEmailResponse,
    tags=["Email"],
    summary="Generate a Plain-Text Summary Email Body",
    responses={
        200: {
            "description": "Summary email body generated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "extraction_id": 1,
                        "approved_risk_count": 2,
                        "message": "Summary email generated with 2 approved risks",
                        "email_body": "ContractIQ Risk Summary — contract\n"
                                      "\n"
                                      "1. Deposit and finance\n"
                                      "   Deposit amount and finance condition assessed.\n"
                                      "2. Settlement date\n"
                                      "   Settlement date and provisions for extension assessed.\n"
                                      "\n"
                                      "This review is a summary and does not replace legal advice "
                                      "on the full contract. Please contact us before signing.\n"
                    }
                }
            }
        },
        404: {
            "description": "Extraction not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Extraction not found with ID: 999"
                    }
                }
            }
        }
    }
)
async def get_summary_email(
    extraction_id: int,
    session: Session = Depends(get_session)
):
    """
    Generate a plain-text summary email body from the approved risks of an extraction.

    **Behavior:**
    - Looks the extraction up by ID (404 if missing).
    - Only risks with `reviewer_status == \"approved\"` are included. Pending
      and rejected risks never appear in the email body.
    - If extraction exists but no risks are approved yet, returns a **200**
      with an empty `email_body` and a message explaining the situation —
      never a 404.
    - The body starts with an intro line naming the matter/property when a
      label can be derived, then lists each approved risk as a numbered
      point (risk_short_desc as the heading, risk_long_desc as the
      explanation) in the style of the reviewer email mockup, and always
      ends with a fixed disclaimer line.

    **cURL Example:**
    ```bash
    curl http://localhost:8000/extractions/1/summary-email
    ```
    """
    try:
        extraction = session.get(ContractExtract, extraction_id)

        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction not found with ID: {extraction_id}"
            )

        approved_risks = session.exec(
            select(ContractRisk)
            .where(
                ContractRisk.extraction_id == extraction.id,
                ContractRisk.reviewer_status == "approved",
            )
            .order_by(ContractRisk.id)
        ).all()

        if not approved_risks:
            logger.info(
                f"Summary email requested for extraction {extraction.id}: "
                f"no approved risks yet"
            )
            return SummaryEmailResponse(
                success=True,
                extraction_id=extraction.id,
                approved_risk_count=0,
                message=(
                    "No approved risks yet; no summary email generated. "
                    "Approve at least one risk to generate an email."
                ),
                email_body="",
            )

        email_lines = [
            f"ContractIQ Risk Summary — {_matter_label(extraction)}",
            "",
        ]
        for idx, risk in enumerate(approved_risks, start=1):
            email_lines.append(f"{idx}. {risk.risk_short_desc}")
            email_lines.append(f"   {risk.risk_long_desc}")
            email_lines.append("")
        email_lines.append(
            "This review is a summary and does not replace legal advice on the "
            "full contract. Please contact us before signing."
        )
        email_lines.append("")

        logger.info(
            f"Generated summary email for extraction {extraction.id} "
            f"with {len(approved_risks)} approved risks"
        )
        return SummaryEmailResponse(
            success=True,
            extraction_id=extraction.id,
            approved_risk_count=len(approved_risks),
            message=(
                f"Summary email generated with {len(approved_risks)} approved risks"
            ),
            email_body="\n".join(email_lines),
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error generating summary email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error generating summary email. Please check server logs."
        )


def _matter_label(extraction) -> str:
    """Best-effort human-readable matter/property label for the email intro."""
    if extraction.extracted_parameters:
        try:
            params = json.loads(extraction.extracted_parameters)
        except (json.JSONDecodeError, TypeError):
            params = None
        if params:
            for param in params:
                name = str(param.get("parameter_name", "")).lower()
                if any(key in name for key in ("address", "property", "matter", "site")):
                    value = param.get("parameter_value")
                    if value:
                        return str(value)
    if extraction.folder_path:
        folder_stem = Path(extraction.folder_path).name.strip()
        if folder_stem:
            return folder_stem
    if extraction.markdown_filename:
        stem = Path(extraction.markdown_filename).stem.strip()
        if stem:
            return stem
    return f"Extraction {extraction.id}"


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    print("Starting Document to Markdown Converter API...")
    print(f"Temporary directory: {TEMP_UPLOAD_DIR}")

    # Database is initialized at module import (see init_db() call above).

    print("Access the API at: http://localhost:8000")
    print("API docs available at: http://localhost:8000/docs")
    print("Alternative docs at: http://localhost:8000/redoc")

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
