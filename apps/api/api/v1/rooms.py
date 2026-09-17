from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import uuid
import asyncio

from core.database import get_db, SessionLocal
from models.user import User
from models.problem import Problem
from models.room import ProblemRoom, RoomMember, RoomMessage
from schemas.room import RoomResponse, MessageResponse, MessageBase
from api.deps import get_current_user
from api.v1.ws import manager
from services.ai.factory import get_ai_provider
from services.ai.agents.problem_orchestrator import ProblemOrchestrator

router = APIRouter()

def get_or_create_ai_bot_user(db: Session) -> User:
    ai_user = db.query(User).filter(User.email == "ai-assistant@solvenow.internal").first()
    if not ai_user:
        ai_user = User(
            email="ai-assistant@solvenow.internal",
            hashed_password="system-managed-bot-account",
            is_active=True,
            is_verified=True,
            reputation_score=500
        )
        db.add(ai_user)
        db.commit()
        db.refresh(ai_user)
    return ai_user

async def process_room_ai_mention(room_id: str, problem_id: uuid.UUID, prompt: str):
    await asyncio.sleep(0.5)
    db = SessionLocal()
    try:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        context = f"Problem: {problem.title}\nDescription: {problem.description}" if problem else ""

        provider = get_ai_provider()
        orchestrator = ProblemOrchestrator(provider)
        res = orchestrator.orchestrate(message=prompt, problem_context=context)
        ai_response_text = res.get("response", "I have reviewed the problem.")

        bot_user = get_or_create_ai_bot_user(db)
        ai_msg = RoomMessage(
            room_id=uuid.UUID(room_id),
            author_id=bot_user.id,
            content=f"🤖 **[SolveNow AI Assistant]**:\n{ai_response_text}"
        )
        db.add(ai_msg)
        db.commit()
        db.refresh(ai_msg)

        await manager.broadcast_to_room(room_id, {
            "type": "message.created",
            "payload": {
                "id": str(ai_msg.id),
                "content": ai_msg.content,
                "author_id": str(ai_msg.author_id),
                "author_email": "ai-assistant@solvenow.internal",
                "created_at": ai_msg.created_at.isoformat()
            }
        })
    except Exception as e:
        # Fallback broadcast error message
        try:
            bot_user = get_or_create_ai_bot_user(db)
            err_msg = RoomMessage(
                room_id=uuid.UUID(room_id),
                author_id=bot_user.id,
                content=f"🤖 **[SolveNow AI]**: Could not complete request: {str(e)}"
            )
            db.add(err_msg)
            db.commit()
            db.refresh(err_msg)
            await manager.broadcast_to_room(room_id, {
                "type": "message.created",
                "payload": {
                    "id": str(err_msg.id),
                    "content": err_msg.content,
                    "author_id": str(err_msg.author_id),
                    "author_email": "ai-assistant@solvenow.internal",
                    "created_at": err_msg.created_at.isoformat()
                }
            })
        except Exception:
            pass
    finally:
        db.close()

@router.get("/problems/{public_id}/room", response_model=RoomResponse)
def get_or_create_room(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    problem = db.query(Problem).filter(Problem.public_id == public_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
        
    room = db.query(ProblemRoom).filter(ProblemRoom.problem_id == problem.id).first()
    if not room:
        room = ProblemRoom(problem_id=problem.id)
        db.add(room)
        db.commit()
        db.refresh(room)
        
    return room

@router.get("/rooms/{room_id}/messages", response_model=List[MessageResponse])
def get_room_messages(
    room_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    room = db.query(ProblemRoom).filter(ProblemRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    if room.problem and not room.problem.is_public:
        member = db.query(RoomMember).filter(RoomMember.room_id == room.id, RoomMember.user_id == current_user.id).first()
        if not member and room.problem.author_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to enter this private room")
            
    messages = db.query(RoomMessage).filter(RoomMessage.room_id == room_id).order_by(RoomMessage.created_at.asc()).all()
    for msg in messages:
        msg.author_username = msg.author.username if msg.author else None
        msg.author_email = msg.author.email if msg.author else None
    return messages

@router.post("/rooms/{room_id}/messages", response_model=MessageResponse)
async def create_message(
    room_id: uuid.UUID,
    msg_in: MessageBase,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    room = db.query(ProblemRoom).filter(ProblemRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
        
    if room.problem and not room.problem.is_public:
        member = db.query(RoomMember).filter(RoomMember.room_id == room.id, RoomMember.user_id == current_user.id).first()
        if not member and room.problem.author_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to post in this private room")
            
    msg = RoomMessage(
        room_id=room_id,
        author_id=current_user.id,
        content=msg_in.content
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg.author_username = current_user.username
    msg.author_email = current_user.email
    
    # Broadcast user's message via WS Manager
    await manager.broadcast_to_room(str(room_id), {
        "type": "message.created",
        "payload": {
            "id": str(msg.id),
            "content": msg.content,
            "author_id": str(msg.author_id),
            "author_email": current_user.email,
            "author_username": current_user.username,
            "created_at": msg.created_at.isoformat()
        }
    })

    # Check for @ai mention in room chat
    content_stripped = msg_in.content.strip()
    if content_stripped.lower().startswith("@ai"):
        ai_query = content_stripped[3:].strip() or "Please help analyze this problem with the room participants."
        asyncio.create_task(process_room_ai_mention(str(room_id), room.problem_id, ai_query))
    
    return msg
