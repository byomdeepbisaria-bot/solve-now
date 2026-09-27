import json
import redis
from core.config import settings

try:
    redis_client = redis.Redis.from_url(settings.REDIS_CONNECTION_URL, decode_responses=True)
except Exception:
    redis_client = None

def publish_notification_event(
    user_id: str,
    event_type: str,
    title: str,
    body: str,
    entity_type: str = None,
    entity_id: str = None,
    action_url: str = None
):
    if not redis_client:
        return
        
    payload = {
        "user_id": str(user_id),
        "type": event_type,
        "title": title,
        "body": body,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "action_url": action_url
    }
    
    # Push to a Redis list acting as a simple message queue
    redis_client.lpush("notifications_queue", json.dumps(payload))

