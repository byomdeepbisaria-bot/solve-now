from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
import uuid
from typing import List, Optional
from pydantic import BaseModel

from core.database import get_db
from models.user import User, Role
from models.expert import ExpertProfile, ExpertRequest, ExpertStatus, RequestStatus
from models.problem import Problem
from models.reputation import UserExpertise
from models.notification import Notification
from models.room import ProblemRoom, RoomMember
from api.deps import get_current_user

router = APIRouter()

@router.get("/search")
def search_experts(limit: int = 4, db: Session = Depends(get_db)):
    # Simple placeholder returning top reputation users
    users = db.query(User).order_by(User.reputation_score.desc()).limit(limit).all()
    return [{
        "user_id": str(u.id), 
        "username": u.email.split('@')[0] if u.email else "Anonymous", 
        "reputation": u.reputation_score,
        "success_rate": 95, # Dummy placeholder
        "avatar": None,
        "expertise": ["Debugging", "System Design"]
    } for u in users]

class ExpertApplyRequest(BaseModel):
    bio: str
    years_experience: int
    timezone: str = "UTC"

class RequestExpertRequest(BaseModel):
    expert_id: uuid.UUID
    message: Optional[str] = None

class ExpertProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    username: str
    status: ExpertStatus
    verification_level: int
    bio: Optional[str]
    timezone: str
    is_available: bool
    years_experience: int
    reputation_score: int
    match_score: Optional[float] = None

    class Config:
        from_attributes = True

@router.get("/search", response_model=List[ExpertProfileResponse])
def search_experts(
    q: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    List verified, available experts — optionally filtered by username or bio.
    Used by the homepage feed and expert discovery UI.
    """
    query = (
        db.query(ExpertProfile, User)
        .join(User, ExpertProfile.user_id == User.id)
        .filter(
            ExpertProfile.status == ExpertStatus.VERIFIED,
            ExpertProfile.is_available == True,
        )
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (func.lower(User.username).contains(q.lower()))
            | (func.lower(ExpertProfile.bio).contains(q.lower()))
        )
    results = query.order_by(desc(User.reputation_score)).limit(limit).all()

    return [
        ExpertProfileResponse(
            id=profile.id,
            user_id=user.id,
            username=user.username,
            status=profile.status,
            verification_level=profile.verification_level,
            bio=profile.bio,
            timezone=profile.timezone,
            is_available=profile.is_available,
            years_experience=profile.years_experience,
            reputation_score=user.reputation_score,
        )
        for profile, user in results
    ]


@router.post("/apply")
def apply_for_expert(
    req: ExpertApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    profile = db.query(ExpertProfile).filter(ExpertProfile.user_id == current_user.id).first()
    if profile:
        raise HTTPException(status_code=400, detail="Already applied")
        
    profile = ExpertProfile(
        user_id=current_user.id,
        bio=req.bio,
        years_experience=req.years_experience,
        timezone=req.timezone,
        status=ExpertStatus.PENDING
    )
    db.add(profile)
    db.commit()
    return {"message": "Application submitted"}

@router.get("/match/{problem_id}", response_model=List[ExpertProfileResponse])
def match_experts(
    problem_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    # Match experts who have verified status and are available
    # Join with UserExpertise based on problem category
    results = db.query(ExpertProfile, User, UserExpertise).join(
        User, ExpertProfile.user_id == User.id
    ).outerjoin(
        UserExpertise, (UserExpertise.user_id == User.id) & (UserExpertise.category_id == problem.category_id)
    ).filter(
        ExpertProfile.status == ExpertStatus.VERIFIED,
        ExpertProfile.is_available == True,
        ExpertProfile.user_id != current_user.id
    ).all()
    
    matches = []
    for profile, user, expertise in results:
        cat_score = expertise.score if expertise else 0
        rep_score = user.reputation_score
        
        # Simple weighted matching formula
        match_score = (cat_score * 0.6) + (rep_score * 0.4)
        
        matches.append(ExpertProfileResponse(
            id=profile.id,
            user_id=user.id,
            username=user.username,
            status=profile.status,
            verification_level=profile.verification_level,
            bio=profile.bio,
            timezone=profile.timezone,
            is_available=profile.is_available,
            years_experience=profile.years_experience,
            reputation_score=user.reputation_score,
            match_score=match_score
        ))
        
    # Sort by match score
    matches.sort(key=lambda x: x.match_score or 0, reverse=True)
    return matches[:10]

@router.post("/problems/{problem_id}/request-expert")
def request_expert(
    problem_id: uuid.UUID,
    req: RequestExpertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    if problem.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only problem owner can request expert")
        
    expert = db.query(ExpertProfile).filter(ExpertProfile.user_id == req.expert_id).first()
    if not expert or expert.status != ExpertStatus.VERIFIED:
        raise HTTPException(status_code=400, detail="Invalid expert")
        
    expert_req = ExpertRequest(
        problem_id=problem.id,
        requester_id=current_user.id,
        expert_id=req.expert_id,
        message=req.message
    )
    db.add(expert_req)

    # Notify Expert
    notification = Notification(
        user_id=req.expert_id,
        type="EXPERT_REQUEST",
        title="New Expert Request",
        body=f"{current_user.username} has requested your expertise for a problem.",
        action_url="/experts/requests"
    )
    db.add(notification)

    db.commit()
    return {"message": "Request sent"}

@router.post("/requests/{req_id}/accept")
def accept_request(
    req_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    expert_req = db.query(ExpertRequest).filter(ExpertRequest.id == req_id).first()
    if not expert_req or expert_req.expert_id != current_user.id:
        raise HTTPException(status_code=404, detail="Request not found")
        
    expert_req.status = RequestStatus.ACCEPTED
    
    # Create private room
    room = ProblemRoom(
        problem_id=expert_req.problem_id,
        is_private=True
    )
    db.add(room)
    db.flush()
    
    # Add Requester and Expert to Room
    db.add(RoomMember(room_id=room.id, user_id=expert_req.requester_id))
    db.add(RoomMember(room_id=room.id, user_id=expert_req.expert_id))
    
    # Notify Requester
    notification = Notification(
        user_id=expert_req.requester_id,
        type="EXPERT_ACCEPTED",
        title="Expert Accepted",
        body=f"{current_user.username} accepted your request! A private room has been created.",
        action_url=f"/problems/{expert_req.problem.public_id}/room"
    )
    db.add(notification)
    
    db.commit()
    return {"message": "Request accepted, private room created"}

@router.patch("/admin/experts/{user_id}/status")
def admin_verify_expert(
    user_id: uuid.UUID,
    status: ExpertStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
        
    profile = db.query(ExpertProfile).filter(ExpertProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    profile.status = status

    # Notify user
    notification = Notification(
        user_id=user_id,
        type="STATUS_UPDATE",
        title="Expert Status Updated",
        body=f"Your expert application status is now: {status.value}",
    )
    db.add(notification)
    db.commit()
    return {"message": f"Status updated to {status.value}"}

@router.get("/requests")
def get_expert_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    requests = db.query(ExpertRequest).filter(
        ExpertRequest.expert_id == current_user.id
    ).order_by(desc(ExpertRequest.created_at)).all()
    
    # Format simple response
    return [{
        "id": req.id,
        "status": req.status,
        "message": req.message,
        "problem": {
            "title": req.problem.title,
            "public_id": req.problem.public_id
        },
        "requester": {
            "username": req.requester.username
        }
    } for req in requests]

