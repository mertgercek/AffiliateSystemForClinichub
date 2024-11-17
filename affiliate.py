from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from models import Affiliate, Referral, Treatment, Ticket, TicketResponse, User, Notification, TreatmentGroup
from extensions import db
from datetime import datetime
from utils import generate_unique_slug, get_ip_location, get_client_ip, format_phone_number, create_notification
from countries import COUNTRIES

bp = Blueprint('affiliate', __name__, url_prefix='/affiliate')

@bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.affiliate:
        # Create affiliate record if missing
        affiliate = Affiliate()
        affiliate.user = current_user
        affiliate.slug = generate_unique_slug()
        db.session.add(affiliate)
        db.session.commit()
    else:
        affiliate = current_user.affiliate
        
    referrals = Referral.query.filter_by(affiliate_id=affiliate.id).order_by(Referral.created_at.desc()).all()
    
    # Serialize referrals for template
    serialized_referrals = []
    for r in referrals:
        referral_data = {
            'created_at': r.created_at.strftime('%Y-%m-%d'),
            'name': r.name,
            'surname': r.surname,
            'treatment_group': r.treatment.group.name if r.treatment and r.treatment.group else 'No Group',
            'email': r.email,
            'phone': r.phone,
            'status': r.status,
            'commission_amount': str(r.commission_amount) if r.commission_amount else '0.00'
        }
        serialized_referrals.append(referral_data)
    
    # Calculate earnings data
    earnings_data = {}
    for referral in referrals:
        if referral.status == 'completed':
            date = referral.created_at.strftime('%Y-%m-%d')
            commission = float(referral.commission_amount) if referral.commission_amount else 0.0
            earnings_data[date] = earnings_data.get(date, 0) + commission
    
    # Get completed and pending referrals
    completed_referrals = [r for r in referrals if r.status == 'completed']
    pending_referrals = [r for r in referrals if r.status != 'completed']

    # Calculate this month's referrals and growth
    current_month = datetime.now().month
    this_month_referrals = len([r for r in referrals if r.created_at.month == current_month])
    last_month_referrals = len([r for r in referrals if r.created_at.month == current_month - 1])
    monthly_growth = ((this_month_referrals - last_month_referrals) / last_month_referrals * 100) if last_month_referrals > 0 else 0
    
    # Calculate success rate
    success_rate = (len(completed_referrals) / len(referrals) * 100) if referrals else 0
    
    # Calculate average commission
    completed_commissions = [float(r.commission_amount or 0) for r in referrals if r.status == 'completed']
    avg_commission = sum(completed_commissions) / len(completed_commissions) if completed_commissions else 0
    
    affiliate_url = url_for('affiliate.landing', slug=affiliate.slug, _external=True)
    
    return render_template('affiliate/dashboard.html',
                         referrals=serialized_referrals,
                         completed_referrals=len(completed_referrals),
                         pending_referrals=len(pending_referrals),
                         affiliate_url=affiliate_url,
                         earnings_data=earnings_data,
                         avg_commission=avg_commission,
                         this_month_referrals=this_month_referrals,
                         monthly_growth=round(monthly_growth, 1),
                         success_rate=round(success_rate, 1))

@bp.route('/<slug>')
def landing(slug):
    affiliate = Affiliate.query.filter_by(slug=slug).first_or_404()
    treatment_groups = TreatmentGroup.query.all()
    return render_template('landing.html', 
                         affiliate=affiliate, 
                         treatment_groups=treatment_groups,
                         countries=COUNTRIES)

@bp.route('/<slug>/referral', methods=['POST'])
def create_referral(slug):
    affiliate = Affiliate.query.filter_by(slug=slug).first_or_404()
    
    # Get the formatted phone number
    phone = request.form.get('formatted_phone')
    if not phone:
        flash('Phone number is required', 'error')
        return redirect(url_for('affiliate.landing', slug=slug))
    
    # Validate required fields
    required_fields = ['name', 'surname', 'email', 'treatment_group_id']
    for field in required_fields:
        if not request.form.get(field):
            flash(f'{field.replace("_", " ").title()} is required', 'error')
            return redirect(url_for('affiliate.landing', slug=slug))
    
    # Validate treatment_group_id is a valid integer
    try:
        treatment_group_id = int(request.form.get('treatment_group_id'))
    except (ValueError, TypeError):
        flash('Please select a valid treatment group', 'error')
        return redirect(url_for('affiliate.landing', slug=slug))
    
    # Get treatment group or return 404
    treatment_group = TreatmentGroup.query.get_or_404(treatment_group_id)
    
    # Get the first active treatment from the group
    treatment = Treatment.query.filter_by(
        group_id=treatment_group.id,
        active=True
    ).first()
    
    if not treatment:
        flash('No active treatments available in this group', 'error')
        return redirect(url_for('affiliate.landing', slug=slug))
    
    # Get IP and location data
    ip_address = get_client_ip(request)
    location_data = get_ip_location(ip_address)
    
    # Create referral
    referral = Referral()
    referral.name = request.form.get('name')
    referral.surname = request.form.get('surname')
    referral.email = request.form.get('email')
    referral.phone = phone  # Already formatted with country code
    referral.treatment_id = treatment.id
    referral.affiliate_id = affiliate.id
    
    if location_data:
        referral.ip_address = ip_address
        referral.country = location_data['country']
        referral.city = location_data['city']
        referral.latitude = location_data['latitude']
        referral.longitude = location_data['longitude']
    
    db.session.add(referral)
    db.session.commit()
    
    flash('Thank you for your interest! We will contact you shortly.', 'success')
    return redirect(url_for('affiliate.landing', slug=slug))

@bp.route('/tickets')
@login_required
def tickets():
    affiliate = current_user.affiliate
    tickets = Ticket.query.filter_by(affiliate_id=affiliate.id).order_by(Ticket.created_at.desc()).all()
    return render_template('affiliate/tickets.html', tickets=tickets)

@bp.route('/tickets/create', methods=['GET', 'POST'])
@login_required
def create_ticket():
    if request.method == 'POST':
        subject = request.form.get('subject')
        message = request.form.get('message')
        priority = request.form.get('priority', 'normal')
        
        if not subject or not message:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('affiliate.create_ticket'))
        
        ticket = Ticket(
            subject=subject,
            message=message,
            priority=priority,
            affiliate_id=current_user.affiliate.id
        )
        
        db.session.add(ticket)
        db.session.commit()
        
        # Create notification for all admins
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(
                user_id=admin.id,
                type='new_ticket',
                message=f'New ticket created by {current_user.username}: {subject}',
                link=url_for('admin.view_ticket', id=ticket.id)
            )
        
        flash('Ticket created successfully.', 'success')
        return redirect(url_for('affiliate.tickets'))
        
    return render_template('affiliate/create_ticket.html')

@bp.route('/ticket/<int:id>')
@login_required
def view_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if ticket.affiliate_id != current_user.affiliate.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('affiliate.tickets'))
    
    return render_template('affiliate/view_ticket.html', ticket=ticket)

@bp.route('/ticket/<int:id>/reply', methods=['POST'])
@login_required
def reply_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if ticket.affiliate_id != current_user.affiliate.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('affiliate.tickets'))
    
    message = request.form.get('message')
    if not message:
        flash('Reply message cannot be empty.', 'danger')
        return redirect(url_for('affiliate.view_ticket', id=id))
    
    response = TicketResponse(
        message=message,
        ticket_id=ticket.id,
        user_id=current_user.id
    )
    
    db.session.add(response)
    db.session.commit()
    
    flash('Reply sent successfully.', 'success')
    return redirect(url_for('affiliate.view_ticket', id=id))

@bp.route('/api/treatments/<int:group_id>')
def get_group_treatments(group_id):
    treatments = Treatment.query.filter_by(
        group_id=group_id,
        active=True
    ).all()
    return jsonify([{
        'id': t.id,
        'name': t.name
    } for t in treatments])
