from flask import Blueprint, jsonify, request, g, current_app
from flask_login import current_user
from functools import wraps
from models import User, APIKey, Affiliate, Referral, Treatment, TreatmentGroup, TreatmentNameMapping
from extensions import db
from datetime import datetime, timedelta
import logging
import time
from collections import defaultdict
from utils import get_client_ip, get_ip_location

bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Rate limiting implementation
RATE_LIMIT = 100  # requests per window
RATE_WINDOW = 3600  # window in seconds (1 hour)
request_counts = defaultdict(list)

def add_cors_headers(response):
    """Add CORS headers to the response"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-API-Key'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

def check_rate_limit(api_key):
    """Check if the request is within rate limits"""
    now = time.time()
    requests = request_counts[api_key]
    
    # Remove old requests outside the window
    while requests and requests[0] < now - RATE_WINDOW:
        requests.pop(0)
    
    # Check if within limit
    if len(requests) >= RATE_LIMIT:
        return False
    
    # Add current request
    requests.append(now)
    return True

@bp.before_request
def handle_preflight():
    """Handle OPTIONS requests"""
    if request.method == 'OPTIONS':
        response = current_app.make_default_options_response()
        return add_cors_headers(response)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip API key check for OPTIONS requests
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
            
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({
                'error': 'Authentication failed',
                'message': 'API key is required',
                'details': 'Include X-API-Key header in your request'
            }), 401

        key = APIKey.query.filter_by(key=api_key, is_active=True).first()
        if not key:
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Invalid or inactive API key',
                'details': 'The provided API key is not valid or has been revoked'
            }), 401

        # Check rate limit
        if not check_rate_limit(api_key):
            return jsonify({
                'error': 'Rate limit exceeded',
                'message': f'Maximum {RATE_LIMIT} requests per {RATE_WINDOW} seconds',
                'details': 'Please wait before making more requests'
            }), 429

        # Update last used timestamp
        key.last_used_at = datetime.utcnow()
        db.session.commit()

        # Store the authenticated user in g
        g.current_user = key.user
        g.start_time = time.time()
        return f(*args, **kwargs)
    return decorated_function

@bp.after_request
def after_request(response):
    """Add CORS headers and log request details after each request"""
    # Add request timing and logging
    if hasattr(g, 'start_time'):
        duration = round((time.time() - g.start_time) * 1000, 2)
        logging.info(f"API Request: {request.method} {request.path} - {response.status_code} - {duration}ms")
        response.headers['X-Response-Time'] = f"{duration}ms"
    
    return add_cors_headers(response)

@bp.errorhandler(405)
def method_not_allowed_error(e):
    logging.warning(f"Method not allowed attempt: {request.method} {request.path}")
    response = jsonify({
        'error': 'Method not allowed',
        'message': f'The method {request.method} is not allowed for this endpoint',
        'allowed_methods': e.valid_methods
    })
    return add_cors_headers(response), 405

@bp.errorhandler(Exception)
def handle_error(e):
    logging.error(f"Unhandled API error: {str(e)}")
    response = jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred',
        'details': str(e) if current_app.debug else None
    })
    return add_cors_headers(response), 500

@bp.route('/referrals/<int:id>/status', methods=['PUT', 'OPTIONS'])
@require_api_key
def update_referral_status(id):
    user = g.current_user
    logging.info(f"User {user.username} attempting to update referral {id} status")
    
    if user.role != 'affiliate':
        logging.warning(f"User {user.username} with role {user.role} attempted to update referral status")
        return jsonify({'error': 'Access denied. User must have affiliate role'}), 403
    
    if not user.affiliate:
        logging.error(f"User {user.username} has affiliate role but no affiliate record")
        return jsonify({'error': 'No affiliate record found. Please contact support'}), 403
    
    referral = Referral.query.get(id)
    if not referral:
        return jsonify({'error': 'Referral not found'}), 404
    
    if referral.affiliate_id != user.affiliate.id:
        return jsonify({'error': 'Access denied. Not authorized to update this referral'}), 403
    
    data = request.json
    if not data or 'status' not in data:
        return jsonify({'error': 'Status field is required'}), 400
    
    new_status = data['status']
    valid_statuses = ['new', 'in-progress', 'completed']
    if new_status not in valid_statuses:
        return jsonify({
            'error': 'Invalid status value',
            'details': f"Status must be one of: {', '.join(valid_statuses)}"
        }), 400
    
    try:
        # Update status
        old_status = referral.status
        referral.status = new_status
        
        # Handle commission calculation for completed status
        if new_status == 'completed' and old_status != 'completed':
            success, message = referral.calculate_and_update_commission()
            if not success:
                db.session.rollback()
                return jsonify({
                    'error': 'Failed to calculate commission',
                    'details': message
                }), 500
        
        db.session.commit()
        logging.info(f"Successfully updated referral {id} status to {new_status}")
        return jsonify(referral.to_dict())
        
    except Exception as e:
        logging.error(f"Error updating referral status: {str(e)}")
        db.session.rollback()
        return jsonify({
            'error': 'Internal server error',
            'details': 'Could not update referral status. Please try again later'
        }), 500

# API Key Management Endpoints
@bp.route('/keys', methods=['POST'])
@require_api_key
def create_api_key():
    try:
        name = request.json.get('name')
        if not name:
            return jsonify({'error': 'Key name is required'}), 400
        
        api_key = g.current_user.generate_api_key(name)
        return jsonify(api_key.to_dict()), 201
    except Exception as e:
        logging.error(f"Error creating API key: {str(e)}")
        return jsonify({'error': 'Could not create API key'}), 500

@bp.route('/keys', methods=['GET'])
@require_api_key
def list_api_keys():
    keys = APIKey.query.filter_by(user_id=g.current_user.id).all()
    return jsonify([key.to_dict() for key in keys])

@bp.route('/keys/<int:key_id>', methods=['DELETE'])
@require_api_key
def revoke_api_key(key_id):
    key = APIKey.query.filter_by(id=key_id, user_id=g.current_user.id).first()
    if not key:
        return jsonify({'error': 'API key not found'}), 404
    
    key.is_active = False
    db.session.commit()
    return '', 204

# Profile endpoint
@bp.route('/profile', methods=['GET'])
@require_api_key
def get_profile():
    user = g.current_user
    if user.affiliate:
        return jsonify({
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'affiliate': {
                'id': user.affiliate.id,
                'approved': user.affiliate.approved,
                'total_earnings': float(user.affiliate.total_earnings or 0)
            }
        })
    return jsonify({
        'username': user.username,
        'email': user.email,
        'role': user.role
    })

# Referrals endpoints
@bp.route('/referrals', methods=['GET'])
@require_api_key
def get_referrals():
    user = g.current_user
    logging.info(f"User {user.username} accessing referrals endpoint")
    
    if user.role != 'affiliate':
        logging.warning(f"User {user.username} with role {user.role} attempted to access referrals")
        return jsonify({'error': 'Access denied. User must have affiliate role'}), 403
    
    if not user.affiliate:
        logging.error(f"User {user.username} has affiliate role but no affiliate record")
        return jsonify({'error': 'No affiliate record found. Please contact support'}), 403
    
    referrals = Referral.query.filter_by(affiliate_id=user.affiliate.id).all()
    return jsonify([referral.to_dict() for referral in referrals])

@bp.route('/referrals', methods=['POST'])
@require_api_key
def create_referral():
    user = g.current_user
    logging.info(f"User {user.username} attempting to create referral")
    
    if user.role != 'affiliate':
        logging.warning(f"User {user.username} with role {user.role} attempted to create referral")
        return jsonify({'error': 'Access denied. User must have affiliate role'}), 403
    
    if not user.affiliate:
        logging.error(f"User {user.username} has affiliate role but no affiliate record")
        return jsonify({'error': 'No affiliate record found. Please contact support'}), 403
    
    data = request.json
    required_fields = ['name', 'surname', 'email', 'phone', 'treatment_id']
    
    if not data or not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    treatment = Treatment.query.get(data['treatment_id'])
    if not treatment or not treatment.active:
        return jsonify({'error': 'Invalid or inactive treatment'}), 400
    
    try:
        referral = Referral(
            affiliate_id=user.affiliate.id,
            treatment_id=treatment.id,
            name=data['name'],
            surname=data['surname'],
            email=data['email'],
            phone=data['phone']
        )
        db.session.add(referral)
        db.session.commit()
        return jsonify(referral.to_dict()), 201
    except Exception as e:
        logging.error(f"Error creating referral: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Could not create referral'}), 500

# Treatments endpoint
@bp.route('/treatments', methods=['GET'])
@require_api_key
def get_treatments():
    treatments = Treatment.query.filter_by(active=True).all()
    return jsonify([treatment.to_dict() for treatment in treatments])

# Statistics endpoint
@bp.route('/stats', methods=['GET'])
@require_api_key
def get_stats():
    user = g.current_user
    logging.info(f"User {user.username} accessing stats endpoint")
    
    if user.role != 'affiliate':
        logging.warning(f"User {user.username} with role {user.role} attempted to access stats")
        return jsonify({
            'error': 'Access denied',
            'details': 'User must have affiliate role to access statistics'
        }), 403
    
    if not user.affiliate:
        logging.error(f"User {user.username} has affiliate role but no affiliate record")
        return jsonify({
            'error': 'No affiliate record found',
            'details': 'User has affiliate role but no associated affiliate record. Please contact support'
        }), 403
    
    try:
        referrals = Referral.query.filter_by(affiliate_id=user.affiliate.id).all()
        total_referrals = len(referrals)
        completed_referrals = len([r for r in referrals if r.status == 'completed'])
        
        stats = {
            'total_referrals': total_referrals,
            'completed_referrals': completed_referrals,
            'conversion_rate': (completed_referrals / total_referrals * 100) if total_referrals > 0 else 0,
            'total_earnings': float(user.affiliate.total_earnings or 0)
        }
        
        logging.info(f"Successfully retrieved stats for affiliate {user.affiliate.id}")
        return jsonify(stats)
        
    except Exception as e:
        logging.error(f"Error retrieving stats for user {user.username}: {str(e)}")
        return jsonify({
            'error': 'Internal server error',
            'details': 'Could not retrieve statistics. Please try again later'
        }), 500

@bp.route('/geoip')
def get_location():
    ip = get_client_ip(request)
    location = get_ip_location(ip)
    if location:
        return jsonify({
            'country_code': location['country']
        })
    return jsonify({
        'country_code': 'TR'  # Default to Turkey
    })

@bp.route('/webhook/treatment-completed', methods=['POST'])
def treatment_completed_webhook():
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['email', 'full_name', 'treatment_name']
    if not all(field in data for field in required_fields):
        return jsonify({
            'success': False,
            'error': 'Missing required fields',
            'required': required_fields
        }), 400
    
    try:
        # Find referral by email
        referral = Referral.query.filter_by(
            email=data['email'].lower().strip()
        ).first()
        
        if not referral:
            return jsonify({
                'success': False,
                'error': 'No matching referral found',
                'details': f"No referral found with email: {data['email']}"
            }), 404
        
        # Find treatment mapping by external name
        mapping = TreatmentNameMapping.query.filter(
            TreatmentNameMapping.external_name.ilike(data['treatment_name'].strip())
        ).first()
        
        if not mapping:
            return jsonify({
                'success': False,
                'error': 'No matching treatment mapping found',
                'details': f"No mapping found for treatment: {data['treatment_name']}"
            }), 404
            
        # Update referral's treatment group and commission
        treatment = Treatment.query.filter_by(
            group_id=mapping.treatment_group_id,
            active=True
        ).first()
        
        if not treatment:
            return jsonify({
                'success': False,
                'error': 'No active treatment found in mapped group',
                'details': 'The mapped treatment group has no active treatments'
            }), 400
        
        # Update referral
        referral.treatment_id = treatment.id
        referral.status = 'completed'
        
        # Calculate commission based on treatment group
        commission = float(mapping.treatment_group.commission_amount or 0)
        referral.commission_amount = commission
        
        # Update affiliate earnings
        referral.affiliate.total_earnings = float(referral.affiliate.total_earnings or 0) + commission
        
        # Create/update treatment status
        if not referral.treatment_status:
            treatment_status = Treatment_Status(
                referral_id=referral.id,
                notes=f"Treatment completed: {data['treatment_name']}"
            )
            db.session.add(treatment_status)
        
        referral.treatment_status.end_date = datetime.utcnow()
        referral.treatment_status.outcome = 'success'
        
        # Trigger webhook notifications
        webhook_data = {
            'id': referral.id,
            'email': referral.email,
            'treatment': treatment.name,
            'commission_amount': commission,
            'affiliate_id': referral.affiliate_id
        }
        trigger_webhook_event('referral.completed', webhook_data, referral.affiliate.user_id)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Referral updated successfully',
            'referral_id': referral.id,
            'commission_amount': commission
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing treatment completion: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e) if current_app.debug else None
        }), 500