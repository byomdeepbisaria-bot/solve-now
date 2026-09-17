from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid

from core.database import get_db
from models.user import User
from models.solution import Solution, SolutionStatus, SolutionVote, SolutionVerification
from models.reputation import UserExpertise
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class CategoryExpertise(BaseModel):
    category_name: str
    score: int

class UserProfileResponse(BaseModel):
    id: uuid.UUID
    username: str
    reputation_score: int
    problems_solved: int
    solutions_verified: int
    success_rate: float
    helpful_votes: int
    expertise: List[CategoryExpertise]

    class Config:
        from_attributes = True

@router.get("/{user_id}/profile", response_model=UserProfileResponse)
def get_user_profile(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Count accepted solutions authored by this user
    problems_solved = db.query(func.count(Solution.id)).filter(
        Solution.author_id == user.id,
        Solution.status == SolutionStatus.ACCEPTED,
    ).scalar() or 0

    total_solutions = db.query(func.count(Solution.id)).filter(
        Solution.author_id == user.id
    ).scalar() or 0

    success_rate = round((problems_solved / total_solutions * 100), 1) if total_solutions > 0 else 0.0

    # Verifications received on this user's solutions (count via join table)
    solutions_verified = (
        db.query(func.count(SolutionVerification.id))
        .join(Solution, SolutionVerification.solution_id == Solution.id)
        .filter(Solution.author_id == user.id)
        .scalar() or 0
    )

    # Upvotes received on this user's solutions (value == 1)
    helpful_votes = (
        db.query(func.count(SolutionVote.id))
        .join(Solution, SolutionVote.solution_id == Solution.id)
        .filter(Solution.author_id == user.id, SolutionVote.value == 1)
        .scalar() or 0
    )

    # Top expertise areas (max 5)
    expertise_records = (
        db.query(UserExpertise)
        .filter(UserExpertise.user_id == user.id)
        .order_by(UserExpertise.score.desc())
        .limit(5)
        .all()
    )
    expertise = [
        CategoryExpertise(category_name=exp.category.name, score=exp.score)
        for exp in expertise_records
        if exp.category
    ]

    return UserProfileResponse(
        id=user.id,
        username=user.username,
        reputation_score=user.reputation_score,
        problems_solved=problems_solved,
        solutions_verified=solutions_verified,
        success_rate=success_rate,
        helpful_votes=helpful_votes,
        expertise=expertise,
    )
