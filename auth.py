from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User, Affiliate
from email_service import send_verification_email
from utils import generate_unique_slug
import secrets

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.register'))

        # Create user
        user = User()
        user.username = username
        user.email = email
        user.set_password(password)
        user.verification_token = secrets.token_urlsafe(32)
        
        # Create affiliate
        affiliate = Affiliate()
        affiliate.user = user
        affiliate.slug = generate_unique_slug()
        
        db.session.add(user)
        db.session.add(affiliate)
        db.session.commit()

        # Send verification email with the token
        try:
            send_verification_email(user.email, user.verification_token)
            flash('Registration successful. Please check your email to verify your account.', 'success')
        except Exception as e:
            flash('Registration successful but verification email could not be sent. Please contact support.', 'warning')
        
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.email_verified:
                flash('Please verify your email first. Check your inbox for the verification link.', 'warning')
                return redirect(url_for('auth.login'))

            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('affiliate.dashboard'))

        flash('Invalid email or password', 'danger')
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if user:
        user.email_verified = True
        user.verification_token = None  # Clear the token after verification
        
        # Auto-approve affiliate if exists
        if user.affiliate:
            user.affiliate.approved = True
            
        db.session.commit()
        flash('Email verified and affiliate approved successfully. You can now log in.', 'success')
    else:
        flash('Invalid or expired verification token.', 'danger')
    return redirect(url_for('auth.login'))

@bp.route('/resend-verification')
@login_required
def resend_verification():
    if current_user.email_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('affiliate.dashboard'))
    
    # Generate new verification token
    current_user.verification_token = secrets.token_urlsafe(32)
    db.session.commit()
    
    try:
        send_verification_email(current_user.email, current_user.verification_token)
        flash('Verification email has been resent. Please check your inbox.', 'success')
    except Exception as e:
        flash('Could not send verification email. Please try again later.', 'danger')
    
    return redirect(url_for('auth.login'))
