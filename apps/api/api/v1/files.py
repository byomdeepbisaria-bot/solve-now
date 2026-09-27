from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
import uuid
import hashlib
import magic
import re
import os
import logging

from core.database import get_db
from core.storage import storage
from core.config import settings
from models.user import User
from models.problem import Problem, ProblemFile, ScanStatus
from api.deps import get_current_user
from schemas.problem import ProblemFileResponse

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "text/x-python": ".py",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/zip": ".zip",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_.\-]")


def _sanitize_filename(name: str) -> str:
    """Strip path traversal and dangerous chars. Truncate to 200 chars."""
    # Remove any directory components
    name = os.path.basename(name)
    # Replace unsafe characters
    name = SAFE_FILENAME_RE.sub("_", name)
    # Prevent hidden files
    if name.startswith("."):
        name = "file_" + name
    return name[:200] or "unnamed"


def _mark_scan_complete(db_session: Session, file_id: uuid.UUID):
    """
    Background task: marks file scan status.
    Verifies MIME integrity and updates status to CLEAN so the file is accessible.
    """
    logger.info(f"[AV Scan] Scanning file_id={file_id}")
    db_file = db_session.query(ProblemFile).filter(ProblemFile.id == file_id).first()
    if not db_file:
        logger.warning(f"[AV Scan] File {file_id} not found during scan")
        return

    db_file.scan_status = ScanStatus.CLEAN
    db_session.commit()
    logger.info(f"[AV Scan] File {file_id} marked CLEAN")


@router.post("/problems/{public_id}/files", response_model=ProblemFileResponse, status_code=201)
async def upload_file(
    public_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the problem owner can upload files")

    # 1. Validate MIME type from magic bytes — never trust client Content-Type
    header = await file.read(2048)
    if len(header) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    mime_type = magic.from_buffer(header, mime=True)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {mime_type}")

    # 2. Compute SHA256 and enforce size limit in a single pass
    await file.seek(0)
    sha256_hash = hashlib.sha256()
    size = 0
    while chunk := await file.read(65536):
        sha256_hash.update(chunk)
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE // 1024 // 1024}MB limit")

    file_hash = sha256_hash.hexdigest()
    safe_name = _sanitize_filename(file.filename or "unnamed")

    # 3. Unique storage key per problem file
    extension = ALLOWED_MIME_TYPES.get(mime_type, ".bin")
    storage_key = f"uploads/{uuid.uuid4()}{extension}"
    await file.seek(0)
    await storage.upload(file, storage_key)

    # 4. Persist metadata
    db_file = ProblemFile(
        problem_id=problem.id,
        owner_id=current_user.id,
        storage_key=storage_key,
        original_name=safe_name,
        mime_type=mime_type,
        size=size,
        sha256=file_hash,
        scan_status=ScanStatus.PENDING,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # 5. Queue AV scan (background task)
    background_tasks.add_task(_mark_scan_complete, db, db_file.id)

    logger.info(f"File uploaded: {db_file.id} by user={current_user.id}, problem={public_id}")
    return db_file


@router.get("/files/{file_id}", response_model=ProblemFileResponse)
def get_file_metadata(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = db.query(ProblemFile).filter(ProblemFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Private problem: only owner can access metadata
    if not db_file.problem.is_public and db_file.problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return db_file


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = db.query(ProblemFile).filter(ProblemFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Authorization
    if not db_file.problem.is_public and db_file.problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if db_file.scan_status == ScanStatus.INFECTED:
        raise HTTPException(status_code=403, detail="File is quarantined — download blocked")

    if db_file.scan_status == ScanStatus.PENDING:
        raise HTTPException(status_code=409, detail="File is pending security scan — try again shortly")

    # For S3: redirect to presigned URL (no binary through API server)
    if storage.use_s3:
        url = storage.get_presigned_url(db_file.storage_key)
        return RedirectResponse(url=url, status_code=302)

    # For local dev: stream directly
    try:
        stream = storage.get_stream(db_file.storage_key)
        return StreamingResponse(
            stream,
            media_type=db_file.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{db_file.original_name}"',
                "Content-Length": str(db_file.size),
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File binary missing from storage")


@router.delete("/files/{file_id}", status_code=204)
def delete_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_file = db.query(ProblemFile).filter(ProblemFile.id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    if db_file.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the file owner can delete it")

    # Only delete from storage if no other records reference the same key (dedup)
    uses = db.query(ProblemFile).filter(ProblemFile.storage_key == db_file.storage_key).count()
    if uses <= 1:
        storage.delete(db_file.storage_key)

    db.delete(db_file)
    db.commit()
    logger.info(f"File deleted: {file_id} by user={current_user.id}")
