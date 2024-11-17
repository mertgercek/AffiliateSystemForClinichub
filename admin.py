from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import User, Affiliate, Referral, Treatment, Treatment_Status, TreatmentGroup, APIKey
from analytics import get_conversion_metrics, get_top_affiliates
from email_service import send_approval_notification
from functools import wraps
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging

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
    affiliates = Affiliate.query.all()
    pending_affiliates = Affiliate.query.filter_by(approved=False).all()
    referrals = Referral.query.order_by(Referral.created_at.desc()).all()
    treatments = Treatment.query.filter_by(active=True).all()
    
    return render_template('admin/dashboard.html',
                         analytics=analytics,
                         top_affiliates=top_affiliates,
                         affiliates=affiliates,
                         pending_affiliates=pending_affiliates,
                         referrals=referrals,
                         treatments=treatments)

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