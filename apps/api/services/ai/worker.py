from sqlalchemy.orm import Session
from services.ai.orchestrator import InvestigationOrchestrator
from models.ai_investigation import AIInvestigation, InvestigationStatus
from models.problem import Problem, ProblemStatus
import logging

logger = logging.getLogger(__name__)


def run_ai_investigation(db: Session, investigation_id: str):
    """
    Background worker task to step the Multi-Agent Investigation orchestrator.
    Loops until it hits a stopping condition (WAITING_FOR_USER, READY, COMPLETED, FAILED).

    IMPORTANT: On any failure, the problem is set to OPEN so it is never stuck
    in AI_PROCESSING and invisible to users.
    """
    investigation = db.query(AIInvestigation).filter(AIInvestigation.id == investigation_id).first()
    if not investigation:
        return

    problem = investigation.problem

    try:
        orchestrator = InvestigationOrchestrator(db, investigation.id)

        stop_states = [
            InvestigationStatus.WAITING_FOR_USER,
            InvestigationStatus.READY,
            InvestigationStatus.COMPLETED,
            InvestigationStatus.FAILED
        ]

        # Simple retry loop for state transitions
        while investigation.status not in stop_states:
            prev_status = investigation.status
            orchestrator.run_cycle()

            # Reload investigation to check new status
            db.refresh(investigation)
            if investigation.status == prev_status:
                # Prevent infinite loop if state didn't change
                logger.warning(f"AI investigation {investigation_id} state did not change — breaking loop")
                break

    except Exception as e:
        logger.error(f"AI investigation {investigation_id} failed with exception: {e}", exc_info=True)
        try:
            investigation.status = InvestigationStatus.FAILED
            investigation.error_message = str(e)
            db.commit()
        except Exception:
            pass

    finally:
        # Regardless of outcome, always unlock the problem.
        # A problem should NEVER stay in AI_PROCESSING — that makes it invisible.
        try:
            db.refresh(problem)
            if problem.status == ProblemStatus.AI_PROCESSING:
                problem.status = ProblemStatus.OPEN
                db.commit()
                logger.info(f"Problem {problem.public_id} promoted to OPEN after AI processing")
        except Exception as e:
            logger.error(f"Failed to promote problem to OPEN: {e}")
