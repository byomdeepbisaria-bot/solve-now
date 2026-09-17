from pydantic import BaseModel
from typing import Optional, List
import uuid
from datetime import datetime
from models.problem import ProblemStatus

class TagBase(BaseModel):
    name: str

class TagResponse(TagBase):
    id: uuid.UUID
    class Config:
        from_attributes = True

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: uuid.UUID
    class Config:
        from_attributes = True

class ProblemBase(BaseModel):
    title: str
    description: str
    priority: Optional[int] = 0
    urgency: Optional[str] = "normal"
    is_public: Optional[bool] = True
    location: Optional[str] = None

class ProblemCreate(ProblemBase):
    category_name: Optional[str] = None
    tags: Optional[List[str]] = []

class ProblemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    urgency: Optional[str] = None
    is_public: Optional[bool] = None
    location: Optional[str] = None
    status: Optional[ProblemStatus] = None

class ProblemFileResponse(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    owner_id: uuid.UUID
    original_name: str
    mime_type: str
    size: int
    scan_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ClarificationResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class FindingResponse(BaseModel):
    id: uuid.UUID
    finding: str
    confidence: float
    evidence: str
    source: str
    class Config:
        from_attributes = True

class CriticReviewResponse(BaseModel):
    id: uuid.UUID
    is_safe: bool
    missing_evidence: Optional[List[str]] = None
    contradictions: Optional[List[str]] = None
    unsafe_instructions: Optional[List[str]] = None
    weak_assumptions: Optional[List[str]] = None
    alternative_explanations: Optional[List[str]] = None
    class Config:
        from_attributes = True

class ProposedSolutionResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    steps: List[str]
    confidence: float
    critic_review: Optional[CriticReviewResponse] = None
    class Config:
        from_attributes = True

class InvestigationResponse(BaseModel):
    id: uuid.UUID
    status: str
    findings: List[FindingResponse] = []
    clarifications: List[ClarificationResponse] = []
    solutions: List[ProposedSolutionResponse] = []
    class Config:
        from_attributes = True

class ProblemResponse(ProblemBase):
    id: uuid.UUID
    public_id: str
    author_id: uuid.UUID
    author_username: Optional[str] = None
    status: ProblemStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    solved_at: Optional[datetime] = None

    category: Optional[CategoryResponse] = None
    tags: List[TagResponse] = []
    files: List[ProblemFileResponse] = []
    investigation: Optional[InvestigationResponse] = None

    class Config:
        from_attributes = True

class PaginatedProblems(BaseModel):
    items: List[ProblemResponse]
    total: int
    page: int
    size: int

