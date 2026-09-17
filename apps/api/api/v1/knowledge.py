from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, desc
import uuid
from typing import List, Optional

from core.database import get_db
from models.knowledge import KnowledgeDocument, KnowledgeStatus
from services.ai.embeddings import generate_embedding
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class KnowledgeSearchResponse(BaseModel):
    id: uuid.UUID
    title: str
    content_snippet: str
    category: Optional[str]
    quality_score: int
    verification_count: int
    relevance: float
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/search", response_model=List[KnowledgeSearchResponse])
def search_knowledge(
    q: Optional[str] = "",

 main
    category: Optional[str] = None,
    verified_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Hybrid Search combining pgvector and Full Text Search.
    When q is empty, returns the most recently published documents.
    Ranking = (Vector Similarity) + (FTS Rank) + (0.1 * log(verification_count + 1)) + (0.01 * quality_score)
    """

    main
    emb = generate_embedding(q)

    # If no embedding (no AI key), fall back to text-only search
    if emb is None:
        base_query = """
            SELECT
                kd.id, kd.title, kd.content, c.name as category,
                kd.quality_score, kd.verification_count, kd.created_at,
                ts_rank_cd(to_tsvector('english', kd.title || ' ' || kd.content), plainto_tsquery('english', :query)) as text_score
            FROM knowledge_documents kd
            LEFT JOIN problem_categories c ON kd.category_id = c.id
            WHERE kd.status = 'PUBLISHED'
        """
        params: dict = {"query": q, "limit": limit}
        filters = []
        if category:
            filters.append("c.name = :category")
            params["category"] = category
        if verified_only:
            filters.append("kd.verification_count > 0")
        if filters:
            base_query += " AND " + " AND ".join(filters)
        final_query = base_query + " ORDER BY text_score DESC LIMIT :limit"
        results = db.execute(text(final_query), params).mappings().all()
        return [
            KnowledgeSearchResponse(
                id=r["id"],
                title=r["title"],
                content_snippet=r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"],
                category=r["category"],
                quality_score=r["quality_score"],
                verification_count=r["verification_count"],
                relevance=float(r["text_score"]),
                created_at=r["created_at"],
            )
            for r in results
        ]

    # Hybrid vector + text search
    vector_str = f"[{','.join(map(str, emb))}]"
    
    base_query = """
        SELECT
            kd.id, kd.title, kd.content, c.name as category,
            kd.quality_score, kd.verification_count, kd.created_at,
            (1.0 - (kd.embedding <=> :vector)) as vector_score,
            ts_rank_cd(to_tsvector('english', kd.title || ' ' || kd.content), plainto_tsquery('english', :query)) as text_score
        FROM knowledge_documents kd
        LEFT JOIN problem_categories c ON kd.category_id = c.id
        WHERE kd.status = 'PUBLISHED'
    """

    filters: list = []
    params = {"query": q, "vector": vector_str, "limit": limit}

    if category:
        filters.append("c.name = :category")
        params["category"] = category

    if verified_only:
        filters.append("kd.verification_count > 0")

    if filters:
        base_query += " AND " + " AND ".join(filters)

    final_query = base_query + """
        ORDER BY (
            (1.0 - (kd.embedding <=> :vector)) * 0.7 +
            ts_rank_cd(to_tsvector('english', kd.title || ' ' || kd.content), plainto_tsquery('english', :query)) * 0.3 +
            LN(kd.verification_count + 1) * 0.1 +
            (kd.quality_score * 0.01)
        ) DESC
        LIMIT :limit
    """

    results = db.execute(text(final_query), params).mappings().all()
    
    response = []
    for r in results:
        # Calculate combined relevance for UI display
        rel = (r["vector_score"] * 0.7) + (r["text_score"] * 0.3)
        response.append(KnowledgeSearchResponse(
            id=r["id"],
            title=r["title"],
            content_snippet=r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"],
            category=r["category"],
            quality_score=r["quality_score"],
            verification_count=r["verification_count"],
            relevance=rel,
            created_at=r["created_at"]
        ))
        
    return response

@router.get("/{document_id}")
def get_knowledge_doc(
    document_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id, KnowledgeDocument.status == KnowledgeStatus.PUBLISHED).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "category": doc.category.name if doc.category else None,
        "quality_score": doc.quality_score,
        "verification_count": doc.verification_count,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at
    }

