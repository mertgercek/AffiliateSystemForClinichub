import requests
import hmac
import hashlib
import json
import logging
from datetime import datetime
from threading import Thread
from flask import current_app
from models import Webhook, db

def generate_signature(payload, secret):
    """Generate HMAC signature for webhook payload"""
    return hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def send_webhook(webhook_id, event_type, data):
    """Send webhook in a separate thread"""
    Thread(target=_send_webhook, args=(webhook_id, event_type, data)).start()

def _send_webhook(webhook_id, event_type, data):
    """Actually send the webhook"""
    with current_app.app_context():
        try:
            webhook = Webhook.query.get(webhook_id)
            if not webhook or not webhook.is_active or event_type not in webhook.events:
                return

            payload = json.dumps({
                'event': event_type,
                'timestamp': datetime.utcnow().isoformat(),
                'data': data
            })

            signature = generate_signature(payload, webhook.secret)
            
            response = requests.post(
                webhook.url,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-Webhook-Signature': signature,
                    'X-Event-Type': event_type
                },
                timeout=5
            )
            
            webhook.last_triggered = datetime.utcnow()
            
            if response.status_code >= 400:
                webhook.failure_count += 1
                if webhook.failure_count >= 5:  # Disable after 5 failures
                    webhook.is_active = False
                    logging.error(f"Webhook {webhook.id} disabled after 5 failures")
            else:
                webhook.failure_count = 0
                
            db.session.commit()
            
        except Exception as e:
            logging.error(f"Error sending webhook {webhook_id}: {str(e)}")
            webhook.failure_count += 1
            if webhook.failure_count >= 5:
                webhook.is_active = False
            db.session.commit()

def trigger_webhook_event(event_type, data, user_id=None):
    """Trigger webhooks for a specific event"""
    query = Webhook.query.filter_by(is_active=True)
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    webhooks = query.all()
    
    for webhook in webhooks:
        if event_type in webhook.events:
            send_webhook(webhook.id, event_type, data) 