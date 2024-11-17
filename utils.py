import string
import random
from models import Affiliate, Notification
import requests
from flask import current_app
from geoip2.database import Reader
from geoip2.errors import AddressNotFoundError
from extensions import db

def generate_unique_slug(length=8):
    characters = string.ascii_letters + string.digits
    while True:
        slug = ''.join(random.choices(characters, k=length))
        if not Affiliate.query.filter_by(slug=slug).first():
            return slug

def format_phone_number(phone):
    # Remove any non-digit characters
    clean_phone = ''.join(filter(str.isdigit, phone))
    if not clean_phone.startswith('+'):
        clean_phone = '+' + clean_phone
    return clean_phone

def verify_recaptcha(token, min_score=0.5):
    try:
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data={
            'secret': current_app.config['RECAPTCHA_SECRET_KEY'],
            'response': token
        })
        result = response.json()
        
        # Check if the score is above minimum threshold
        if result.get('success') and result.get('score', 0) >= min_score:
            return True
        return False
    except Exception as e:
        current_app.logger.error(f"reCAPTCHA verification error: {e}")
        return False

def get_ip_location(ip_address):
    """Get location data from IP address using GeoLite2"""
    try:
        # For testing/development, return dummy data for localhost
        if ip_address in ['127.0.0.1', 'localhost']:
            return {
                'country': 'TR',
                'city': 'Istanbul',
                'latitude': 41.0082,
                'longitude': 28.9784
            }
            
        with Reader('GeoLite2-City.mmdb') as reader:
            response = reader.city(ip_address)
            return {
                'country': response.country.iso_code,
                'city': response.city.name,
                'latitude': response.location.latitude,
                'longitude': response.location.longitude
            }
    except AddressNotFoundError:
        # Return default location for testing
        return {
            'country': 'TR',
            'city': 'Istanbul',
            'latitude': 41.0082,
            'longitude': 28.9784
        }
    except Exception as e:
        print(f"Error getting location for IP {ip_address}: {str(e)}")
        return None

def get_client_ip(request):
    """Get client's real IP address"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0]
    return request.remote_addr

def create_notification(user_id, type, message, link=None):
    """Create a new notification"""
    notification = Notification(
        user_id=user_id,
        type=type,
        message=message,
        link=link
    )
    db.session.add(notification)
    db.session.commit()
