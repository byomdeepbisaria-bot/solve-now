import time
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text
from nanoid import generate

from core.database import get_db
from models.user import User
from models.problem import Problem, Category, Tag, ProblemStatus, problem_tags
from schemas.problem import ProblemCreate, ProblemUpdate, ProblemResponse, PaginatedProblems
from api.deps import get_current_user, get_current_user_optional

router = APIRouter()

from services.ai.worker import run_ai_investigation
from services.ai.embeddings import generate_embedding
from models.ai_investigation import AIInvestigation
from core.config import settings

class ProblemDraft(BaseModel):
    title: str
    description: str

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
 main

@router.post("/similar")
def find_similar_problems(
    draft: ProblemDraft,
    db: Session = Depends(get_db)
):
    text_to_embed = f"{draft.title}\n{draft.description}"
    emb = generate_embedding(text_to_embed)

    if not emb:
        # No AI key — fall back to simple text search
        problems = db.query(Problem).filter(
            Problem.is_public == True,
            Problem.title.ilike(f"%{draft.title[:30]}%")
        ).limit(5).all()
    else:
        problems = db.query(Problem).filter(
            Problem.embedding.cosine_distance(emb) < 0.2,
            Problem.is_public == True
        ).order_by(Problem.embedding.cosine_distance(emb)).limit(5).all()

    return [{"public_id": p.public_id, "title": p.title, "status": p.status} for p in problems]

@router.post("", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED)
def create_problem(
    *,
    db: Session = Depends(get_db),
    problem_in: ProblemCreate,
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    public_id = generate(size=10)
    
    # Handle category
    category_id = None
    if problem_in.category_name:
        category = db.query(Category).filter(Category.name == problem_in.category_name).first()
        if not category:
            category = Category(name=problem_in.category_name)
            db.add(category)
            db.flush()
        category_id = category.id

    # Generate embedding
    emb = generate_embedding(f"{problem_in.title}\n{problem_in.description}")

    # Moderation analysis
    from services.moderation import analyze_content, record_flags
    analysis = analyze_content(f"{problem_in.title} {problem_in.description}")
    
    # If high risk, block immediately
    if analysis["risk_level"] == "HIGH":
        raise HTTPException(status_code=400, detail="Content blocked by automated moderation.")

    db_problem = Problem(
        public_id=public_id,
        author_id=current_user.id,
        title=problem_in.title,
        description=problem_in.description,
        priority=problem_in.priority,
        urgency=problem_in.urgency,
        is_public=problem_in.is_public,
        location=problem_in.location,
        category_id=category_id,
        status=ProblemStatus.AI_PROCESSING,
        embedding=emb,
        is_hidden=(analysis["risk_level"] == "MEDIUM")
    )
    db.add(db_problem)
    db.flush()

    # Record any flags
    record_flags(db, "problem", str(db_problem.id), analysis)

    # Handle tags
    if problem_in.tags:
        for tag_name in problem_in.tags:
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            db_problem.tags.append(tag)

    # Create AI Investigation record
    investigation = AIInvestigation(
        problem_id=db_problem.id,
        provider=settings.AI_PROVIDER,
        model=settings.AI_MODEL
    )
    db.add(investigation)

    db.commit()
    db.refresh(db_problem)
    db.refresh(investigation)
    
    # Trigger AI structuring
    background_tasks.add_task(run_ai_investigation, db, investigation.id)
    
    return db_problem

@router.get("", response_model=PaginatedProblems)
def get_problems(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    limit: Optional[int] = Query(None, ge=1, le=100),  # alias for size
    is_public: Optional[bool] = None,
    status: Optional[ProblemStatus] = None,
    category: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    # Allow ?limit= as an alias for ?size= (frontend compatibility)
    if limit is not None:
        size = limit
    query = db.query(Problem)
    
    if current_user:
        if is_public is not None:
            if is_public:
                query = query.filter(Problem.is_public == True, Problem.is_hidden == False)
            else:
                query = query.filter(Problem.author_id == current_user.id, Problem.is_public == False)
        else:
            query = query.filter(((Problem.is_public == True) & (Problem.is_hidden == False)) | (Problem.author_id == current_user.id))
    else:
        query = query.filter(Problem.is_public == True, Problem.is_hidden == False)

    if status:
        query = query.filter(Problem.status == status)
        
    if category:
        query = query.join(Category).filter(Category.name == category)

    total = query.count()
    items = query.order_by(desc(Problem.created_at)).offset((page - 1) * size).limit(size).all()
    
    for item in items:
        item.author_username = item.author.username if item.author else None
    
    return PaginatedProblems(items=items, total=total, page=page, size=size)

@router.get("/search", response_model=PaginatedProblems)
def search_problems(
    q: Optional[str] = "",
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    if not q.strip():
        return PaginatedProblems(items=[], total=0, page=page, size=size)

    from models.problem import _USE_PGVECTOR
    emb = generate_embedding(q)
    offset = (page - 1) * size

    if _USE_PGVECTOR and emb:
        # Hybrid vector + full-text search
        vector_str = f"[{','.join(map(str, emb))}]"
        query = f"""
            SELECT p.id,
                (1.0 - (p.embedding <=> :vector)) * 0.7 +
                ts_rank_cd(to_tsvector('english', p.title || ' ' || p.description),
                           plainto_tsquery('english', :query)) * 0.3 AS score
            FROM problems p
            WHERE p.is_public = TRUE AND p.is_hidden = FALSE
            ORDER BY score DESC
            LIMIT :limit OFFSET :offset
        """
        results = db.execute(text(query), {"query": q, "vector": vector_str, "limit": size, "offset": offset}).mappings().all()
    else:
        # Full-text only fallback (no pgvector needed)
        query = """
            SELECT p.id,
                ts_rank_cd(to_tsvector('english', p.title || ' ' || p.description),
                           plainto_tsquery('english', :query)) AS score
            FROM problems p
            WHERE p.is_public = TRUE AND p.is_hidden = FALSE
              AND to_tsvector('english', p.title || ' ' || p.description)
                  @@ plainto_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :limit OFFSET :offset
        """
        results = db.execute(text(query), {"query": q, "limit": size, "offset": offset}).mappings().all()

    if not results:
        return PaginatedProblems(items=[], total=0, page=page, size=size)

    ids = [r["id"] for r in results]
    problems = db.query(Problem).filter(Problem.id.in_(ids)).all()
    problems_sorted = sorted(problems, key=lambda x: ids.index(x.id))

    total_query = "SELECT count(*) FROM problems WHERE is_public = TRUE AND is_hidden = FALSE"
    total = db.execute(text(total_query)).scalar()
    
    for p in problems_sorted:
        p.author_username = p.author.username if p.author else None

    return PaginatedProblems(items=problems_sorted, total=total, page=page, size=size)

@router.get("/{public_id}", response_model=ProblemResponse)
def get_problem(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    
    if not problem.is_public or problem.is_hidden:
        if not current_user or problem.author_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions to view this problem")
            
    problem.author_username = problem.author.username if problem.author else None
        
    return problem

@router.patch("/{public_id}", response_model=ProblemResponse)
def update_problem(
    public_id: str,
    problem_in: ProblemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    update_data = problem_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(problem, field, value)
        
    db.commit()
    db.refresh(problem)
    
    # Re-trigger AI
    if problem.investigation and (problem_in.title or problem_in.description):
        background_tasks.add_task(run_ai_investigation, db, problem.investigation.id)
        
    return problem

@router.delete("/{public_id}")
def delete_problem(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    db.delete(problem)
    db.commit()
    return {"message": "Problem deleted successfully"}

class ClarificationAnswer(BaseModel):
    answer: str

@router.post("/{public_id}/clarifications/{clarification_id}", response_model=ProblemResponse)
def answer_clarification(
    public_id: str,
    clarification_id: str,
    answer_in: ClarificationAnswer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    from models.ai_investigation import ProblemClarification
    
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    clarification = db.query(ProblemClarification).filter(ProblemClarification.id == clarification_id).first()
    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")
        
    clarification.answer = answer_in.answer
    clarification.answered_at = datetime.now(timezone.utc)
    db.commit()
    
    # Re-trigger AI structuring with new info
    if problem.investigation:
        background_tasks.add_task(run_ai_investigation, db, problem.investigation.id)
        
    db.refresh(problem)
    return problem
