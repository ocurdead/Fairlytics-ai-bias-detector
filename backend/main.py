from typing import Any, Dict
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from core.orchestrator import run_model_only_orchestration, run_orchestration
from services.input_processor import parse_csv_bytes, validate_for_audit

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS: Dict[str, pd.DataFrame] = {}
AUDITS: Dict[str, Dict[str, Any]] = {}


class RunAuditRequest(BaseModel):
    upload_id: str
    protected_attr: str = ""
    label_col: str
    favorable_label: str


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.post("/upload-dataset")
async def upload_dataset(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for dataset input.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    df = parse_csv_bytes(content)
    upload_id = str(uuid4())
    UPLOADS[upload_id] = df
    preview = df.head(5).fillna("").to_dict(orient="records")
    return {
        "upload_id": upload_id,
        "row_count": len(df),
        "columns": df.columns.tolist(),
        "preview_rows": preview,
    }


@app.post("/run-dataset-audit")
def run_dataset_audit(req: RunAuditRequest):
    df = UPLOADS.get(req.upload_id)
    if df is None:
        raise HTTPException(status_code=404, detail="upload_id not found.")

    errors, quality = validate_for_audit(df, req.protected_attr, req.label_col, req.favorable_label)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    resolved_columns = quality["resolved_columns"]
    protected_attr = resolved_columns["protected_attr"]
    label_col = resolved_columns["label_col"]

    clean_df = df.dropna(subset=[protected_attr, label_col]).copy()
    result = run_orchestration(clean_df, protected_attr, label_col, req.favorable_label)
    audit_id = str(uuid4())
    AUDITS[audit_id] = {"status": "complete", "quality": quality, "result": result}
    return {"audit_id": audit_id, "status": "complete"}


@app.post("/upload-model")
async def upload_model(
    model_file: UploadFile = File(...),
    model_name: str = Form("uploaded_model"),
    model_notes: str = Form(""),
):
    content = await model_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded model file is empty.")

    result = run_model_only_orchestration(model_name=model_name, model_notes=model_notes)
    audit_id = str(uuid4())
    AUDITS[audit_id] = {"status": "complete", "quality": {"mode": "model_upload"}, "result": result}
    return {"audit_id": audit_id, "status": "complete"}


@app.get("/results/{audit_id}")
def get_results(audit_id: str):
    payload = AUDITS.get(audit_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="audit_id not found.")
    return payload
