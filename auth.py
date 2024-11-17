from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User, Affiliate
from email_service import send_verification_email
from utils import generate_unique_slug, verify_recaptcha, get_client_ip, get_ip_location
import secrets
from datetime import datetime, timedelta
import hashlib

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        recaptcha_token = request.form.get('recaptcha_token')
        if not verify_recaptcha(recaptcha_token, min_score=0.5):
            flash('Security check failed. Please try again.', 'error')
            return redirect(url_for('auth.register'))

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.register'))

        # Create user with verification token
        user = User()
        user.username = username
        user.email = email
        user.set_password(password)
        user.verification_token = secrets.token_urlsafe(32)
        user.token_expiry = datetime.utcnow() + timedelta(hours=24)  # Token expires in 24 hours
        
        # Create affiliate with location data
        affiliate = Affiliate()
        affiliate.user = user
        affiliate.slug = generate_unique_slug()
        
        # Get IP and location data
        ip_address = get_client_ip(request)
        location_data = get_ip_location(ip_address)
        
        if location_data:
            affiliate.ip_address = ip_address
            affiliate.country = location_data['country']
            affiliate.city = location_data['city']
            affiliate.latitude = location_data['latitude']
            affiliate.longitude = location_data['longitude']
        
        try:
            db.session.add(user)
            db.session.add(affiliate)
            db.session.commit()

            # Send verification email after successful database commit
            if send_verification_email(user.email, user.verification_token):
                flash('Registration successful. Please check your email to verify your account.', 'success')
            else:
                current_app.logger.error(f"Failed to send verification email to {user.email}")
                flash('Registration successful but verification email could not be sent. Please contact support.', 'warning')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during registration: {str(e)}")
            flash('An error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('auth.register'))
        
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@bp.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash('Invalid verification link.', 'danger')
        return redirect(url_for('auth.login'))
        
    if user.token_expiry and user.token_expiry < datetime.utcnow():
        flash('Verification link has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.resend_verification'))
        
    user.verify_email()
    
    flash('Email verified successfully! You can now log in.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('No account found with that email address.', 'danger')
            return redirect(url_for('auth.resend_verification'))
            
        if user.email_verified:
            flash('This email is already verified.', 'info')
            return redirect(url_for('auth.login'))
            
        # Generate new verification token
        user.verification_token = secrets.token_urlsafe(32)
        user.token_expiry = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        
        try:
            send_verification_email(user.email, user.verification_token)
            flash('Verification email sent. Please check your inbox.', 'success')
        except Exception as e:
            flash('Error sending verification email. Please try again later.', 'danger')
            
        return redirect(url_for('auth.login'))
        
    return render_template('resend_verification.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        recaptcha_token = request.form.get('recaptcha_token')
        if not verify_recaptcha(recaptcha_token, min_score=0.5):
            flash('Security check failed. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.email_verified:
                flash('Please verify your email address first.', 'warning')
                return redirect(url_for('auth.resend_verification'))
                
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """Handle email unsubscribe requests"""
    # Verify token
    try:
        # Find user by reversing the token generation
        for user in User.query.all():
            check_token = hashlib.sha256(f"{user.email}:{current_app.config['SECRET_KEY']}".encode()).hexdigest()
            if check_token == token:
                # Update user preferences
                user.email_subscribed = False
                db.session.commit()
                flash('You have been successfully unsubscribed from our emails.', 'success')
                return redirect(url_for('auth.login'))
        
        flash('Invalid unsubscribe link.', 'danger')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        current_app.logger.error(f"Error processing unsubscribe request: {str(e)}")
        flash('Error processing your request. Please contact support.', 'danger')
        return redirect(url_for('auth.login'))
