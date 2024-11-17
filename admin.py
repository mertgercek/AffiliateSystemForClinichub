from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User, Affiliate, Referral, Treatment, Treatment_Status, TreatmentGroup, APIKey, Ticket, TicketResponse, Notification, Webhook, TreatmentNameMapping
from analytics import get_conversion_metrics, get_top_affiliates, get_country_stats
from email_service import send_verification_email, send_welcome_email, send_referral_notification, send_approval_notification
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import secrets
import csv
import io
from werkzeug.utils import secure_filename
from sqlalchemy.sql import extract
from countries import COUNTRIES
import psutil
import platform
import flask
import os
from sqlalchemy.sql import text

bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You need to be an admin to access this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    analytics = get_conversion_metrics()
    top_affiliates = get_top_affiliates()
    country_stats = get_country_stats()
    
    # Get total referrals count
    total_referrals = Referral.query.count()
    
    # Calculate this month's referrals and growth
    current_month = datetime.utcnow().month
    current_year = datetime.utcnow().year
    
    this_month_referrals = Referral.query.filter(
        extract('month', Referral.created_at) == current_month,
        extract('year', Referral.created_at) == current_year
    ).count()
    
    last_month_referrals = Referral.query.filter(
        extract('month', Referral.created_at) == (current_month - 1 if current_month > 1 else 12),
        extract('year', Referral.created_at) == (current_year if current_month > 1 else current_year - 1)
    ).count()
    
    monthly_growth = ((this_month_referrals - last_month_referrals) / last_month_referrals * 100) if last_month_referrals > 0 else 0
    
    affiliates = Affiliate.query.all()
    pending_affiliates = Affiliate.query.filter_by(approved=False).all()
    referrals = Referral.query.order_by(Referral.created_at.desc()).all()
    treatments = Treatment.query.filter_by(active=True).all()
    
    return render_template('admin/dashboard.html',
                         analytics=analytics,
                         top_affiliates=top_affiliates,
                         country_stats=country_stats,
                         affiliates=affiliates,
                         pending_affiliates=pending_affiliates,
                         referrals=referrals,
                         treatments=treatments,
                         total_referrals=total_referrals,
                         monthly_growth=round(monthly_growth, 1),
                         countries=COUNTRIES)

@bp.route('/treatment-groups')
@login_required
@admin_required
def manage_treatment_groups():
    treatment_groups = TreatmentGroup.query.all()
    return render_template('admin/treatment_groups.html', treatment_groups=treatment_groups)

@bp.route('/treatment-group/add', methods=['POST'])
@login_required
@admin_required
def add_treatment_group():
    name = request.form.get('name')
    description = request.form.get('description')
    commission_amount = request.form.get('commission_amount')
    
    try:
        commission_amount = Decimal(commission_amount or '0')
        if commission_amount < 0:
            raise ValueError("Commission amount cannot be negative")
            
        group = TreatmentGroup()
        group.name = name
        group.description = description
        group.commission_amount = commission_amount
        
        db.session.add(group)
        db.session.commit()
        flash('Treatment group added successfully.', 'success')
    except (ValueError, InvalidOperation):
        flash('Invalid commission amount.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash('Error adding treatment group.', 'danger')
    
    return redirect(url_for('admin.manage_treatment_groups'))

@bp.route('/treatment-group/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_treatment_group(id):
    group = TreatmentGroup.query.get_or_404(id)
    try:
        commission_amount = Decimal(request.form.get('commission_amount') or '0')
        if commission_amount < 0:
            raise ValueError("Commission amount cannot be negative")
            
        group.name = request.form.get('name')
        group.description = request.form.get('description')
        group.commission_amount = commission_amount
        
        # Recalculate commissions for all referrals in this group's treatments
        for treatment in group.treatments:
            for referral in treatment.referrals:
                if referral.status == 'completed':
                    referral.calculate_and_update_commission()
                    referral.affiliate.update_earnings()
        
        db.session.commit()
        flash('Treatment group updated successfully.', 'success')
    except (ValueError, InvalidOperation):
        flash('Invalid commission amount.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash('Error updating treatment group.', 'danger')
    
    return redirect(url_for('admin.manage_treatment_groups'))

@bp.route('/affiliate/<int:id>/commission', methods=['POST'])
@login_required
@admin_required
def update_commission_rate(id):
    affiliate = Affiliate.query.get_or_404(id)
    try:
        commission_rate = Decimal(request.form.get('commission_rate') or '0')
        if commission_rate < 0 or commission_rate > 100:
            raise ValueError("Commission rate must be between 0 and 100")
            
        # Update commission rate and recalculate earnings
        affiliate.commission_rate = commission_rate
        
        # Recalculate commissions for all completed referrals
        for referral in affiliate.referrals:
            if referral.status == 'completed':
                referral.calculate_and_update_commission()
        
        # Update total earnings
        affiliate.update_earnings()
        
        db.session.commit()
        flash('Commission rate updated successfully.', 'success')
    except (ValueError, InvalidOperation):
        flash('Invalid commission rate.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash('Error updating commission rate.', 'danger')
    
    return redirect(url_for('admin.dashboard'))

@bp.route('/treatments')
@login_required
@admin_required
def manage_treatments():
    treatments = Treatment.query.all()
    treatment_groups = TreatmentGroup.query.all()
    return render_template('admin/treatments.html', 
                         treatments=treatments,
                         treatment_groups=treatment_groups)

@bp.route('/treatment/add', methods=['POST'])
@login_required
@admin_required
def add_treatment():
    name = request.form.get('name')
    description = request.form.get('description')
    group_id = request.form.get('group_id')
    
    treatment = Treatment()
    treatment.name = name
    treatment.description = description
    treatment.group_id = group_id if group_id else None
    
    db.session.add(treatment)
    db.session.commit()
    flash('Treatment added successfully.', 'success')
    return redirect(url_for('admin.manage_treatments'))

@bp.route('/treatment/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_treatment(id):
    treatment = Treatment.query.get_or_404(id)
    treatment.name = request.form.get('name')
    treatment.description = request.form.get('description')
    treatment.group_id = request.form.get('group_id')
    
    # Recalculate commissions if group changed
    if treatment.group_id and treatment.referrals:
        for referral in treatment.referrals:
            if referral.status == 'completed':
                referral.calculate_and_update_commission()
                referral.affiliate.update_earnings()
    
    db.session.commit()
    flash('Treatment updated successfully.', 'success')
    return redirect(url_for('admin.manage_treatments'))

@bp.route('/treatment/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_treatment(id):
    treatment = Treatment.query.get_or_404(id)
    treatment.active = not treatment.active
    db.session.commit()
    flash(f'Treatment {"activated" if treatment.active else "deactivated"} successfully.', 'success')
    return redirect(url_for('admin.manage_treatments'))

@bp.route('/treatment/<int:id>/status', methods=['GET', 'POST'])
@login_required
@admin_required
def update_treatment_status(id):
    referral = Referral.query.get_or_404(id)
    
    if request.method == 'POST':
        status = request.form.get('status')
        notes = request.form.get('notes')
        
        try:
            if not referral.treatment_status:
                treatment_status = Treatment_Status()
                treatment_status.referral_id = referral.id
                treatment_status.start_date = datetime.utcnow() if status == 'in-progress' else None
                treatment_status.notes = notes
                db.session.add(treatment_status)
            else:
                treatment_status = referral.treatment_status
                treatment_status.notes = notes
                
                if status == 'in-progress' and not treatment_status.start_date:
                    treatment_status.start_date = datetime.utcnow()
                elif status == 'completed' and not treatment_status.end_date:
                    treatment_status.end_date = datetime.utcnow()
            
            # Update referral status
            referral.status = status
            
            # Calculate commission only when status becomes 'completed'
            if status == 'completed':
                logging.info(f"Processing commission for completed referral {referral.id}")
                success, message = referral.calculate_and_update_commission()
                if success:
                    flash('Treatment status updated and commission calculated successfully.', 'success')
                else:
                    flash(f'Treatment status updated but commission calculation failed: {message}', 'warning')
            else:
                flash('Treatment status updated successfully.', 'success')
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating treatment status: {str(e)}")
            flash('Error updating treatment status.', 'danger')
            
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/treatment_status.html', referral=referral)

@bp.route('/analytics')
@login_required
@admin_required
def get_analytics():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        analytics = get_conversion_metrics(start_date=start_date, end_date=end_date)
    else:
        analytics = get_conversion_metrics()
    
    return jsonify(analytics)

@bp.route('/affiliate/<int:id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_affiliate(id):
    affiliate = Affiliate.query.get_or_404(id)
    affiliate.approved = True
    affiliate.user.email_verified = True
    db.session.commit()
    
    try:
        send_approval_notification(affiliate.user.email)
    except Exception as e:
        flash('Affiliate approved but notification email could not be sent.', 'warning')
    else:
        flash('Affiliate approved and email verified successfully', 'success')
    
    return redirect(url_for('admin.dashboard'))

@bp.route('/affiliate/<int:id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_affiliate(id):
    affiliate = Affiliate.query.get_or_404(id)
    db.session.delete(affiliate)
    db.session.commit()
    flash('Affiliate rejected', 'success')
    return redirect(url_for('admin.dashboard'))

@bp.route('/affiliate/<int:id>/details')
@login_required
@admin_required
def affiliate_details(id):
    affiliate = Affiliate.query.get_or_404(id)
    
    # Get all referrals for this affiliate
    referrals = Referral.query.filter_by(affiliate_id=affiliate.id)\
                              .order_by(Referral.created_at.desc()).all()
    
    # Calculate analytics
    total_referrals = len(referrals)
    completed_referrals = sum(1 for r in referrals if r.status == 'completed')
    conversion_rate = (completed_referrals / total_referrals * 100) if total_referrals > 0 else 0
    
    # Calculate average commission for completed referrals
    completed_commissions = [float(r.commission_amount) for r in referrals if r.status == 'completed']
    avg_commission = sum(completed_commissions) / len(completed_commissions) if completed_commissions else 0
    
    # Get status distribution for pie chart
    status_counts = {}
    for referral in referrals:
        status_counts[referral.status] = status_counts.get(referral.status, 0) + 1
    
    # Get monthly commission distribution for bar chart
    commission_distribution = {}
    for referral in referrals:
        if referral.status == 'completed':
            month = referral.created_at.strftime('%Y-%m')
            commission_distribution[month] = commission_distribution.get(month, 0) + float(referral.commission_amount)
    
    analytics = {
        'total_referrals': total_referrals,
        'conversion_rate': round(conversion_rate, 2),
        'avg_commission': round(avg_commission, 2),
        'status_counts': status_counts,
        'commission_distribution': commission_distribution
    }
    
    return render_template('admin/affiliate_details.html',
                         affiliate=affiliate,
                         referrals=referrals,
                         analytics=analytics)

@bp.route('/api-keys')
@login_required
@admin_required
def manage_api_keys():
    api_keys = APIKey.query.filter_by(user_id=current_user.id).order_by(APIKey.created_at.desc()).all()
    return render_template('admin/api_keys.html', api_keys=api_keys)

@bp.route('/api-key/create', methods=['POST'])
@login_required
@admin_required
def create_api_key():
    name = request.form.get('name')
    if not name:
        flash('Key name is required', 'danger')
        return redirect(url_for('admin.manage_api_keys'))
    
    try:
        api_key = current_user.generate_api_key(name)
        flash('API key created successfully', 'success')
    except Exception as e:
        logging.error(f"Error creating API key: {str(e)}")
        flash('Could not create API key', 'danger')
    
    return redirect(url_for('admin.manage_api_keys'))

@bp.route('/api-key/<int:key_id>/revoke', methods=['POST'])
@login_required
@admin_required
def revoke_api_key(key_id):
    key = APIKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not key:
        flash('API key not found', 'danger')
        return redirect(url_for('admin.manage_api_keys'))
    
    key.is_active = False
    db.session.commit()
    flash('API key revoked successfully', 'success')
    return redirect(url_for('admin.manage_api_keys'))

@bp.route('/api-docs')
@login_required
@admin_required
def api_docs():
    return render_template('admin/api_docs.html')

@bp.route('/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    # Get all referrals for each user with affiliate
    user_referrals = {}
    for user in users:
        if user.affiliate:
            user_referrals[user.id] = Referral.query.filter_by(affiliate_id=user.affiliate.id).all()
    return render_template('admin/users.html', users=users, user_referrals=user_referrals)

@bp.route('/user/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    # Don't allow editing the main admin account
    if user.email == 'admin@clinichub.com':
        flash('Cannot modify the main admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    user.username = request.form.get('username')
    user.email = request.form.get('email')
    user.role = request.form.get('role')
    
    # Handle password change if provided
    new_password = request.form.get('new_password')
    if new_password:
        user.set_password(new_password)
    
    # Handle email verification status
    email_verified = request.form.get('email_verified') == 'true'
    user.email_verified = email_verified
    
    try:
        db.session.commit()
        flash('User updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating user.', 'danger')
    
    return redirect(url_for('admin.manage_users'))

@bp.route('/user/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    
    # Don't allow deleting the main admin account
    if user.email == 'admin@clinichub.com':
        flash('Cannot delete the main admin account.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting user.', 'danger')
    
    return redirect(url_for('admin.manage_users'))

@bp.route('/tickets')
@login_required
@admin_required
def manage_tickets():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template('admin/tickets.html', tickets=tickets)

@bp.route('/ticket/<int:id>')
@login_required
@admin_required
def view_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    admins = User.query.filter_by(role='admin').all()
    return render_template('admin/view_ticket.html', ticket=ticket, admins=admins)

@bp.route('/ticket/<int:id>/update', methods=['POST'])
@login_required
@admin_required
def update_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    
    status = request.form.get('status')
    priority = request.form.get('priority')
    assigned_admin_id = request.form.get('assigned_admin_id')
    
    if status:
        ticket.status = status
    if priority:
        ticket.priority = priority
    if assigned_admin_id:
        ticket.assigned_admin_id = int(assigned_admin_id)
    
    db.session.commit()
    flash('Ticket updated successfully.', 'success')
    return redirect(url_for('admin.view_ticket', id=id))

@bp.route('/ticket/<int:id>/reply', methods=['POST'])
@login_required
@admin_required
def reply_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    message = request.form.get('message')
    
    if not message:
        flash('Reply message cannot be empty.', 'danger')
        return redirect(url_for('admin.view_ticket', id=id))
    
    response = TicketResponse(
        message=message,
        ticket_id=ticket.id,
        user_id=current_user.id
    )
    
    db.session.add(response)
    db.session.commit()
    
    flash('Reply sent successfully.', 'success')
    return redirect(url_for('admin.view_ticket', id=id))

@bp.route('/api/referral-heatmap')
@login_required
@admin_required
def referral_heatmap_data():
    # Get filter parameters
    days = request.args.get('days', 'all')
    status = request.args.get('status', 'all')
    
    # Base query
    query = Referral.query.filter(
        Referral.latitude.isnot(None),
        Referral.longitude.isnot(None)
    )
    
    # Apply filters
    if days != 'all':
        days = int(days)
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Referral.created_at >= cutoff_date)
        
    if status != 'all':
        query = query.filter(Referral.status == status)
    
    referrals = query.all()
    
    # Calculate intensity based on status and recency
    def calculate_intensity(referral):
        # Base intensity
        intensity = 1.0
        
        # Increase intensity for completed referrals
        if referral.status == 'completed':
            intensity *= 1.5
        elif referral.status == 'in-progress':
            intensity *= 1.2
            
        # Adjust intensity based on commission amount
        if referral.commission_amount:
            commission = float(referral.commission_amount)
            if commission > 0:
                intensity *= min(1 + (commission / 1000), 2)  # Cap at 2x
                
        return min(intensity, 2)  # Cap final intensity at 2
    
    data = [{
        'lat': r.latitude,
        'lng': r.longitude,
        'intensity': calculate_intensity(r),
        'status': r.status,
        'created_at': r.created_at.strftime('%Y-%m-%d')
    } for r in referrals]
    
    return jsonify(data)

@bp.route('/heatmap-content')
@login_required
@admin_required
def heatmap_content():
    return render_template('admin/heatmap_content.html')

@bp.route('/heatmap')
@login_required
@admin_required
def referral_heatmap():
    return render_template('admin/heatmap.html')

@bp.route('/api/new-tickets-count')
@login_required
@admin_required
def new_tickets_count():
    count = Ticket.query.filter_by(status='open').count()
    return jsonify({'count': count})

@bp.route('/affiliate/<int:id>/map')
@login_required
@admin_required
def affiliate_map_content(id):
    affiliate = Affiliate.query.get_or_404(id)
    return render_template('admin/affiliate_map_content.html', affiliate=affiliate)

@bp.route('/notifications')
@login_required
@admin_required
def notifications():
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    return render_template('admin/notifications.html', notifications=notifications)

@bp.route('/api/notifications')
@login_required
@admin_required
def get_notifications():
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        read=False
    ).order_by(Notification.created_at.desc()).all()
    return jsonify([n.to_dict() for n in notifications])

@bp.route('/notification/<int:id>/mark-read', methods=['POST'])
@login_required
@admin_required
def mark_notification_read(id):
    notification = Notification.query.get_or_404(id)
    notification.read = True
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@admin_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id).update({'read': True})
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/referrals')
@login_required
@admin_required
def manage_referrals():
    referrals = Referral.query.order_by(Referral.created_at.desc()).all()
    return render_template('admin/referrals.html', referrals=referrals)

@bp.route('/referral/<int:id>/status', methods=['POST'])
@login_required
@admin_required
def update_referral_status(id):
    referral = Referral.query.get_or_404(id)
    data = request.get_json()
    old_status = referral.status
    
    try:
        referral.status = data['status']
        db.session.commit()
        
        # Trigger webhook for status update
        webhook_data = {
            'id': referral.id,
            'old_status': old_status,
            'new_status': referral.status,
            'affiliate_id': referral.affiliate_id,
            'treatment_id': referral.treatment_id
        }
        
        if referral.status == 'completed':
            trigger_webhook_event('referral.completed', webhook_data, referral.affiliate.user_id)
        else:
            trigger_webhook_event('referral.updated', webhook_data, referral.affiliate.user_id)
            
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/referral/<int:id>/notes', methods=['POST'])
@login_required
@admin_required
def update_referral_notes(id):
    referral = Referral.query.get_or_404(id)
    data = request.get_json()
    
    try:
        if not referral.treatment_status:
            treatment_status = Treatment_Status(referral_id=referral.id)
            db.session.add(treatment_status)
            referral.treatment_status = treatment_status
            
        referral.treatment_status.notes = data['notes']
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/api/affiliate/<int:affiliate_id>/referrals')
@login_required
@admin_required
def get_affiliate_referrals(affiliate_id):
    referrals = Referral.query.filter_by(affiliate_id=affiliate_id).order_by(Referral.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'created_at': r.created_at.strftime('%Y-%m-%d'),
        'name': r.name,
        'surname': r.surname,
        'email': r.email,
        'phone': r.phone,
        'treatment_name': r.treatment.name,
        'status': r.status,
        'country': r.country,
        'city': r.city,
        'notes': r.treatment_status.notes if r.treatment_status else ''
    } for r in referrals])

@bp.route('/webhooks')
@login_required
@admin_required
def manage_webhooks():
    webhooks = Webhook.query.filter_by(user_id=current_user.id).all()
    return render_template('admin/webhooks.html', webhooks=webhooks)

@bp.route('/webhook/create', methods=['POST'])
@login_required
@admin_required
def create_webhook():
    name = request.form.get('name')
    url = request.form.get('url')
    events = request.form.getlist('events')
    
    if not name or not url or not events:
        flash('All fields are required', 'danger')
        return redirect(url_for('admin.manage_webhooks'))
    
    webhook = Webhook(
        user_id=current_user.id,
        name=name,
        url=url,
        events=events,
        secret=secrets.token_hex(32)
    )
    
    db.session.add(webhook)
    db.session.commit()
    
    flash('Webhook created successfully', 'success')
    return redirect(url_for('admin.manage_webhooks'))

@bp.route('/webhook/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_webhook(id):
    webhook = Webhook.query.get_or_404(id)
    if webhook.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('admin.manage_webhooks'))
    
    webhook.is_active = not webhook.is_active
    webhook.failure_count = 0  # Reset failure count when re-enabling
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': webhook.is_active})

@bp.route('/webhook/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_webhook(id):
    webhook = Webhook.query.get_or_404(id)
    if webhook.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('admin.manage_webhooks'))
    
    db.session.delete(webhook)
    db.session.commit()
    
    flash('Webhook deleted successfully', 'success')
    return redirect(url_for('admin.manage_webhooks'))

@bp.route('/treatment-mappings')
@login_required
@admin_required
def manage_treatment_mappings():
    mappings = TreatmentNameMapping.query.order_by(TreatmentNameMapping.external_name).all()
    treatment_groups = TreatmentGroup.query.all()
    return render_template('admin/treatment_mappings.html', 
                         mappings=mappings,
                         treatment_groups=treatment_groups)

@bp.route('/treatment-mapping/create', methods=['POST'])
@login_required
@admin_required
def create_treatment_mapping():
    external_name = request.form.get('external_name')
    treatment_group_id = request.form.get('treatment_group_id')
    
    if not external_name or not treatment_group_id:
        flash('All fields are required', 'danger')
        return redirect(url_for('admin.manage_treatment_mappings'))
    
    mapping = TreatmentNameMapping(
        external_name=external_name.strip(),
        treatment_group_id=treatment_group_id
    )
    
    try:
        db.session.add(mapping)
        db.session.commit()
        flash('Mapping created successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error creating mapping', 'danger')
        
    return redirect(url_for('admin.manage_treatment_mappings'))

@bp.route('/treatment-mapping/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_treatment_mapping(id):
    mapping = TreatmentNameMapping.query.get_or_404(id)
    
    mapping.external_name = request.form.get('external_name', '').strip()
    mapping.treatment_group_id = request.form.get('treatment_group_id')
    
    try:
        db.session.commit()
        flash('Mapping updated successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating mapping', 'danger')
        
    return redirect(url_for('admin.manage_treatment_mappings'))

@bp.route('/treatment-mapping/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_treatment_mapping(id):
    mapping = TreatmentNameMapping.query.get_or_404(id)
    
    try:
        db.session.delete(mapping)
        db.session.commit()
        flash('Mapping deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting mapping', 'danger')
        
    return redirect(url_for('admin.manage_treatment_mappings'))

@bp.route('/bulk-upload')
@login_required
@admin_required
def bulk_upload():
    return render_template('admin/bulk_upload.html')

@bp.route('/download-template/<type>')
@login_required
@admin_required
def download_template(type):
    templates = {
        'treatment_groups': 'name,description,commission_amount\nGroup 1,Description 1,100.00',
        'treatments': 'name,description,group_name,active,average_duration\nTreatment 1,Description 1,Group 1,true,30',
        'mappings': 'external_name,treatment_group_name\nExternal Treatment 1,Group 1'
    }
    
    if type not in templates:
        flash('Invalid template type', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    output = io.StringIO()
    output.write(templates[type])
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={type}_template.csv'}
    )

@bp.route('/bulk-upload/treatment-groups', methods=['POST'])
@login_required
@admin_required
def bulk_upload_treatment_groups():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    file = request.files['file']
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_data = csv.DictReader(stream)
        
        success_count = 0
        error_details = []
        
        for row in csv_data:
            try:
                group = TreatmentGroup(
                    name=row['name'].strip(),
                    description=row['description'].strip(),
                    commission_amount=float(row['commission_amount'])
                )
                db.session.add(group)
                success_count += 1
            except Exception as e:
                error_details.append(f"Error with row {row['name']}: {str(e)}")
        
        db.session.commit()
        
        results = {
            'success': True,
            'message': f'Successfully imported {success_count} treatment groups',
            'details': error_details if error_details else None
        }
        
    except Exception as e:
        results = {
            'success': False,
            'message': 'Error processing file',
            'details': [str(e)]
        }
    
    return render_template('admin/bulk_upload.html', results=results)

@bp.route('/bulk-upload/treatments', methods=['POST'])
@login_required
@admin_required
def bulk_upload_treatments():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    file = request.files['file']
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_data = csv.DictReader(stream)
        
        success_count = 0
        error_details = []
        
        for row in csv_data:
            try:
                # Find or create treatment group
                group = TreatmentGroup.query.filter_by(name=row['group_name'].strip()).first()
                if not group:
                    error_details.append(f"Treatment group not found: {row['group_name']}")
                    continue
                
                treatment = Treatment(
                    name=row['name'].strip(),
                    description=row['description'].strip(),
                    group_id=group.id,
                    active=row['active'].lower() == 'true',
                    average_duration=int(row['average_duration'])
                )
                db.session.add(treatment)
                success_count += 1
            except Exception as e:
                error_details.append(f"Error with row {row['name']}: {str(e)}")
        
        db.session.commit()
        
        results = {
            'success': True,
            'message': f'Successfully imported {success_count} treatments',
            'details': error_details if error_details else None
        }
        
    except Exception as e:
        results = {
            'success': False,
            'message': 'Error processing file',
            'details': [str(e)]
        }
    
    return render_template('admin/bulk_upload.html', results=results)

@bp.route('/bulk-upload/mappings', methods=['POST'])
@login_required
@admin_required
def bulk_upload_mappings():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    file = request.files['file']
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_data = csv.DictReader(stream)
        
        success_count = 0
        error_details = []
        
        for row in csv_data:
            try:
                # Find treatment group
                group = TreatmentGroup.query.filter_by(name=row['treatment_group_name'].strip()).first()
                if not group:
                    error_details.append(f"Treatment group not found: {row['treatment_group_name']}")
                    continue
                
                mapping = TreatmentNameMapping(
                    external_name=row['external_name'].strip(),
                    treatment_group_id=group.id
                )
                db.session.add(mapping)
                success_count += 1
            except Exception as e:
                error_details.append(f"Error with row {row['external_name']}: {str(e)}")
        
        db.session.commit()
        
        results = {
            'success': True,
            'message': f'Successfully imported {success_count} mappings',
            'details': error_details if error_details else None
        }
        
    except Exception as e:
        results = {
            'success': False,
            'message': 'Error processing file',
            'details': [str(e)]
        }
    
    return render_template('admin/bulk_upload.html', results=results)

@bp.route('/country-stats')
@login_required
@admin_required
def country_stats():
    stats = get_country_stats()
    return render_template('admin/country_stats.html', country_stats=stats)

@bp.route('/api/country-stats/<country>')
@login_required
@admin_required
def get_country_details(country):
    # Get detailed stats for specific country
    referrals = Referral.query.filter_by(country=country).all()
    completed = [r for r in referrals if r.status == 'completed']
    
    # Calculate monthly trends
    monthly_trends = {}
    for referral in referrals:
        month = referral.created_at.strftime('%Y-%m')
        monthly_trends[month] = monthly_trends.get(month, 0) + 1
    
    return jsonify({
        'total_referrals': len(referrals),
        'completed_referrals': len(completed),
        'completion_rate': (len(completed) / len(referrals) * 100) if referrals else 0,
        'total_commission': sum(float(r.commission_amount or 0) for r in completed),
        'monthly_trends': monthly_trends
    })

@bp.route('/system-status')
@login_required
@admin_required
def system_status():
    # Get system information
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    
    # Format uptime string
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    
    # Get database size
    with db.engine.connect() as conn:
        db_size = conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    
    # Get active sessions
    active_sessions = db.session.query(User).filter(User.last_seen >= datetime.utcnow() - timedelta(minutes=5)).count()
    
    return render_template('admin/system_status.html',
                         uptime=uptime_str,
                         python_version=platform.python_version(),
                         flask_version=flask.__version__,
                         db_size=db_size,
                         active_sessions=active_sessions,
                         recent_errors=get_recent_errors())

@bp.route('/server-logs')
@login_required
@admin_required
def server_logs():
    return render_template('admin/server_logs.html')

@bp.route('/api/resource-usage')
@login_required
@admin_required
def get_resource_usage():
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    
    return jsonify({
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_used': memory.used,
        'memory_total': memory.total,
        'uptime': f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
    })

@bp.route('/api/logs')
@login_required
@admin_required
def get_logs():
    try:
        with open('logs/error.log', 'r') as f:
            logs = []
            for line in f:
                try:
                    timestamp, message = line.split(' - ', 1)
                    logs.append({
                        'id': len(logs) + 1,
                        'timestamp': timestamp.strip(),
                        'level': 'ERROR',
                        'message': message.strip()
                    })
                except:
                    continue
        
        # If no logs exist, create some test logs but don't recursively call
        if not logs:
            current_app.logger.error("Test error message")
            current_app.logger.error("Another test error message")
            
            # Read the file again after creating test logs
            with open('logs/error.log', 'r') as f:
                for line in f:
                    try:
                        timestamp, message = line.split(' - ', 1)
                        logs.append({
                            'id': len(logs) + 1,
                            'timestamp': timestamp.strip(),
                            'level': 'ERROR',
                            'message': message.strip()
                        })
                    except:
                        continue
                        
        return jsonify({'logs': logs})
        
    except FileNotFoundError:
        # Create logs directory and file if they don't exist
        os.makedirs('logs', exist_ok=True)
        open('logs/error.log', 'a').close()
        return jsonify({'logs': []})

@bp.route('/api/logs/clear', methods=['POST'])
@login_required
@admin_required
def clear_logs():
    try:
        open('logs/error.log', 'w').close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def get_recent_errors(limit=10):
    errors = []
    try:
        with open('logs/app.log', 'r') as f:
            lines = f.readlines()
            for line in reversed(lines):
                try:
                    if ' - ' not in line:
                        continue
                        
                    timestamp, rest = line.split(' - ', 1)
                    if ':' not in rest:
                        continue
                        
                    level_part, message = rest.split(':', 1)
                    log_level = level_part.strip()
                    
                    if log_level in ['ERROR', 'WARNING']:
                        errors.append({
                            'timestamp': timestamp.strip(),
                            'level': log_level,
                            'message': message.strip()
                        })
                        if len(errors) >= limit:
                            break
                except Exception as e:
                    current_app.logger.error(f"Error parsing log line: {str(e)}")
                    continue
    except FileNotFoundError:
        current_app.logger.warning("Log file not found")
        os.makedirs('logs', exist_ok=True)
        open('logs/app.log', 'a').close()
    except Exception as e:
        current_app.logger.error(f"Error reading logs: {str(e)}")
    
    return errors

@bp.route('/api-tester')
@login_required
@admin_required
def api_tester():
    return render_template('admin/api_tester.html')

@bp.route('/email-tester')
@login_required
@admin_required
def email_tester():
    return render_template('admin/email_tester.html')

@bp.route('/api/test-email', methods=['POST'])
@login_required
@admin_required
def test_email():
    data = request.get_json()
    template = data.get('template')
    email = data.get('email')
    test_data = data.get('data', {})
    
    try:
        if template == 'verification':
            send_verification_email(
                email=email, 
                token=test_data.get('verification_link', 'test-token')
            )
        elif template == 'welcome':
            send_welcome_email(
                email=email, 
                username=test_data.get('username', 'Test User')
            )
        elif template == 'referral_created':
            send_referral_notification(
                email=email,
                referral_data={
                    'name': test_data.get('patient_name', 'Test Patient'),
                    'treatment_name': test_data.get('treatment_name', 'Test Treatment'),
                    'affiliate_name': test_data.get('affiliate_name', 'Test Affiliate')
                }
            )
        elif template == 'referral_completed':
            send_referral_notification(
                email=email,
                referral_data={
                    'name': test_data.get('patient_name', 'Test Patient'),
                    'treatment_name': test_data.get('treatment_name', 'Test Treatment'),
                    'status': 'completed',
                    'commission_amount': test_data.get('commission_amount', 100)
                }
            )
        elif template == 'commission_paid':
            send_referral_notification(
                email=email,
                referral_data={
                    'name': test_data.get('patient_name', 'Test Patient'),
                    'treatment_name': test_data.get('treatment_name', 'Test Treatment'),
                    'commission_amount': test_data.get('commission_amount', 100),
                    'payment_method': test_data.get('payment_method', 'Bank Transfer')
                }
            )
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error sending test email: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/pending-affiliates')
@login_required
@admin_required
def pending_affiliates():
    pending = Affiliate.query.filter_by(approved=False).all()
    return render_template('admin/pending_affiliates.html', pending_affiliates=pending)

@bp.route('/api/resend-verification', methods=['POST'])
@login_required
@admin_required
def resend_verification():
    data = request.get_json()
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})
        
    user.verification_token = secrets.token_urlsafe(32)
    user.token_expiry = datetime.utcnow() + timedelta(hours=24)
    db.session.commit()
    
    try:
        send_verification_email(user.email, user.verification_token)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})