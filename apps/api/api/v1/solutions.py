from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc
from typing import List
import uuid
import logging

from core.database import get_db
from models.user import User
from models.problem import Problem, ProblemStatus
from models.solution import Solution, SolutionVote, SolutionVerification, SolutionComment, SolutionStatus
from schemas.solution import SolutionCreate, SolutionUpdate, SolutionResponse, SolutionVoteCreate, SolutionCommentCreate, SolutionCommentResponse
from api.deps import get_current_user, get_current_user_optional
from services.ai.knowledge_worker import run_knowledge_extraction
from services.reputation import ReputationService, ReputationRules

router = APIRouter()
logger = logging.getLogger(__name__)


def get_solution_with_stats(db: Session, solution: Solution, current_user_id: uuid.UUID = None) -> SolutionResponse:
    """
    Returns solution with aggregated vote/verification stats.
    Uses separate scalar queries to avoid table-name duplication errors in multi-join.
    """
    upvotes = db.query(func.count(SolutionVote.id)).filter(
        SolutionVote.solution_id == solution.id,
        SolutionVote.value == 1
    ).scalar() or 0

    downvotes = db.query(func.count(SolutionVote.id)).filter(
        SolutionVote.solution_id == solution.id,
        SolutionVote.value == -1
    ).scalar() or 0

    verifications = db.query(func.count(SolutionVerification.id)).filter(
        SolutionVerification.solution_id == solution.id
    ).scalar() or 0

    user_vote = 0
    if current_user_id:
        vote = db.query(SolutionVote.value).filter(
            SolutionVote.solution_id == solution.id,
            SolutionVote.user_id == current_user_id
        ).scalar()
        if vote is not None:
            user_vote = vote

    resp = SolutionResponse.model_validate(solution)
    resp.upvotes = int(upvotes)
    resp.downvotes = int(downvotes)
    resp.verification_count = int(verifications)
    resp.user_vote = user_vote
    return resp



@router.post("/problems/{problem_id_or_public_id}/solutions", response_model=SolutionResponse, status_code=status.HTTP_201_CREATED)
def create_solution(
    problem_id_or_public_id: str,
    solution_in: SolutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        val_uuid = uuid.UUID(problem_id_or_public_id)
        problem = db.query(Problem).filter((Problem.id == val_uuid) | (Problem.public_id == problem_id_or_public_id)).first()
    except ValueError:
        problem = db.query(Problem).filter(Problem.public_id == problem_id_or_public_id).first()

    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    # Moderation analysis
    from services.moderation import analyze_content, record_flags
    analysis = analyze_content(solution_in.content)
    
    if analysis["risk_level"] == "HIGH":
        raise HTTPException(status_code=400, detail="Content blocked by automated moderation.")
        
    solution = Solution(
        problem_id=problem.id,
        author_id=current_user.id,
        content=solution_in.content,
        is_hidden=(analysis["risk_level"] == "MEDIUM")
    )
    db.add(solution)
    db.commit()
    db.refresh(solution)
    
    record_flags(db, "solution", str(solution.id), analysis)
    return solution

@router.get("/problems/{public_id}/solutions", response_model=List[SolutionResponse])
def get_solutions(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional)
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
main

@router.post("/solutions/{solution_id}/vote")
def vote_solution(
    solution_id: uuid.UUID,
    vote_in: SolutionVoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    solution = db.query(Solution).filter(Solution.id == solution_id).first()
    if not solution:
        raise HTTPException(status_code=404, detail="Solution not found")
        
    if solution.author_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot vote on your own solution")
        
    vote = db.query(SolutionVote).filter(
        SolutionVote.solution_id == solution.id,
        SolutionVote.user_id == current_user.id
    ).first()
    
    rep_service = ReputationService(db)
    val = getattr(vote_in, "value", None)
    if val is None:
        val = getattr(vote_in, "vote_value", 0)
    category_id = solution.problem.category_id if solution.problem else None
    
    if vote:
        if val == 0:
            # Revert old vote
            if vote.value == 1:
                rep_service.revoke_points(solution.author_id, "UPVOTE", ReputationRules.UPVOTE_RECEIVED, solution.problem_id, solution.id)
            elif vote.value == -1:
                rep_service.revoke_points(solution.author_id, "DOWNVOTE", ReputationRules.DOWNVOTE_RECEIVED, solution.problem_id, solution.id)
            db.delete(vote)
        else:
            if vote.value != val:
                # Revert old
                if vote.value == 1:
                    rep_service.revoke_points(solution.author_id, "UPVOTE", ReputationRules.UPVOTE_RECEIVED, solution.problem_id, solution.id)
                elif vote.value == -1:
                    rep_service.revoke_points(solution.author_id, "DOWNVOTE", ReputationRules.DOWNVOTE_RECEIVED, solution.problem_id, solution.id)
                
                # Apply new
                vote.value = val
                if val == 1:
                    rep_service.award_points(solution.author_id, "UPVOTE_RECEIVED", ReputationRules.UPVOTE_RECEIVED, solution.problem_id, solution.id, category_id)
                elif val == -1:
                    rep_service.award_points(solution.author_id, "DOWNVOTE_RECEIVED", ReputationRules.DOWNVOTE_RECEIVED, solution.problem_id, solution.id, category_id)
    else:
        if val != 0:
            vote = SolutionVote(
                solution_id=solution.id,
                user_id=current_user.id,
                value=val
            )
            db.add(vote)
            if val == 1:
                rep_service.award_points(solution.author_id, "UPVOTE_RECEIVED", ReputationRules.UPVOTE_RECEIVED, solution.problem_id, solution.id, category_id)
            elif val == -1:
                rep_service.award_points(solution.author_id, "DOWNVOTE_RECEIVED", ReputationRules.DOWNVOTE_RECEIVED, solution.problem_id, solution.id, category_id)
                
    db.commit()
    return {"message": "Vote recorded"}

@router.post("/solutions/{solution_id}/verify")
def verify_solution(
    solution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    solution = db.query(Solution).filter(Solution.id == solution_id).first()
    if not solution:
        raise HTTPException(status_code=404, detail="Solution not found")
        
    if solution.author_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot verify your own solution")
        
    verification = db.query(SolutionVerification).filter(
        SolutionVerification.solution_id == solution.id,
        SolutionVerification.user_id == current_user.id
    ).first()
    
    if verification:
        raise HTTPException(status_code=400, detail="Already verified this solution")
        
    new_verification = SolutionVerification(
        solution_id=solution.id,
        user_id=current_user.id
    )
    db.add(new_verification)
    
    rep_service = ReputationService(db)
    category_id = solution.problem.category_id if solution.problem else None
    rep_service.award_points(solution.author_id, "SOLUTION_VERIFIED", ReputationRules.SOLUTION_VERIFIED, solution.problem_id, solution.id, category_id)
    
    db.commit()
    return {"message": "Solution verified"}

@router.post("/solutions/{solution_id}/accept")
def accept_solution(
    solution_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    solution = db.query(Solution).filter(Solution.id == solution_id).first()
    if not solution:
        raise HTTPException(status_code=404, detail="Solution not found")
        
    problem = solution.problem
    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only problem owner can accept a solution")
        
    solution.status = SolutionStatus.ACCEPTED
    problem.status = ProblemStatus.SOLVED
    problem.solved_at = func.now()
    
    rep_service = ReputationService(db)
    rep_service.award_points(solution.author_id, "SOLUTION_ACCEPTED", ReputationRules.SOLUTION_ACCEPTED, problem.id, solution.id, problem.category_id)
    
    db.commit()
    
    # Send notification via Redis
    from services.events import publish_notification_event
    publish_notification_event(
        user_id=str(solution.author_id),
        event_type="SOLUTION_ACCEPTED",
        title="Solution Accepted!",
        body=f"Your solution for '{problem.title}' has been accepted.",
        entity_type="problem",
        entity_id=str(problem.id),
        action_url=f"/problems/{problem.public_id}"
    )
    
    background_tasks.add_task(run_knowledge_extraction, db, problem.id, solution.id)
    
    return {"message": "Solution accepted"}
