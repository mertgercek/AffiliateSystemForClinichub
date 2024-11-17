from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from models import Affiliate, Referral, Treatment
from extensions import db
from datetime import datetime
from utils import generate_unique_slug

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
    treatments = Treatment.query.filter_by(active=True).all()
    return render_template('landing.html', affiliate=affiliate, treatments=treatments)

@bp.route('/<slug>/referral', methods=['POST'])
def create_referral(slug):
    affiliate = Affiliate.query.filter_by(slug=slug).first_or_404()
    treatment = Treatment.query.get_or_404(request.form.get('treatment_id'))
    
    referral = Referral()
    referral.affiliate = affiliate
    referral.treatment = treatment
    referral.name = request.form.get('name')
    referral.surname = request.form.get('surname')
    referral.email = request.form.get('email')
    referral.phone = request.form.get('phone')
    
    db.session.add(referral)
    db.session.commit()
    
    flash('Referral submitted successfully.', 'success')
    return redirect(url_for('affiliate.landing', slug=slug))
