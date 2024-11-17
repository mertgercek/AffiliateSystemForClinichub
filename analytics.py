from datetime import datetime, timedelta
from sqlalchemy import func, case, extract, text
from models import User, Referral, Treatment, Affiliate, Treatment_Status, TreatmentGroup
from extensions import db

def get_conversion_metrics(affiliate_id=None, start_date=None, end_date=None):
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    # Base query for referrals within date range
    base_query = Referral.query.filter(
        Referral.created_at.between(start_date, end_date)
    )
    
    # Add affiliate filter if specified
    if affiliate_id:
        base_query = base_query.filter(Referral.affiliate_id == affiliate_id)
    
    # Total referrals
    total_referrals = base_query.count()
    
    # Total commissions paid
    total_commissions = db.session.query(
        func.sum(Referral.commission_amount)
    ).filter(
        Referral.status == 'completed',
        Referral.created_at.between(start_date, end_date)
    ).scalar() or 0
    
    # Referrals by status
    status_counts = dict(
        base_query.with_entities(
            Referral.status, 
            func.count(Referral.id)
        ).group_by(Referral.status).all()
    )
    
    # Calculate conversion rate
    completed = status_counts.get('completed', 0)
    conversion_rate = (completed / total_referrals * 100) if total_referrals > 0 else 0
    
    # Commission distribution by treatment group
    commission_by_group = db.session.query(
        TreatmentGroup.name,
        func.sum(Referral.commission_amount)
    ).join(
        Treatment, TreatmentGroup.id == Treatment.group_id
    ).join(
        Referral, Treatment.id == Referral.treatment_id
    ).filter(
        Referral.status == 'completed',
        Referral.created_at.between(start_date, end_date)
    ).group_by(TreatmentGroup.name).all()
    
    commission_distribution = {str(k): float(v or 0) for k, v in commission_by_group}
    
    # Treatment success rates and commissions
    treatment_stats = db.session.query(
        Treatment.name,
        func.count(Referral.id).label('total'),
        func.sum(case((Treatment_Status.outcome == 'success', 1), else_=0)).label('successful'),
        func.avg(case(
            (Treatment_Status.end_date != None, 
             func.extract('epoch', Treatment_Status.end_date - Treatment_Status.start_date) / 86400),
            else_=None
        )).label('avg_duration'),
        func.sum(Referral.commission_amount).label('total_commission'),
        TreatmentGroup.commission_amount.label('fixed_commission')
    ).select_from(Treatment).join(
        Referral, Treatment.id == Referral.treatment_id
    ).outerjoin(
        Treatment_Status, Referral.id == Treatment_Status.referral_id
    ).outerjoin(
        TreatmentGroup, Treatment.group_id == TreatmentGroup.id
    ).filter(
        Referral.created_at.between(start_date, end_date)
    ).group_by(Treatment.name, TreatmentGroup.commission_amount).all()
    
    treatment_distribution = {str(stat[0]): stat[1] for stat in treatment_stats}
    treatment_success_rate = {
        str(stat[0]): (stat[2] / stat[1] * 100) if stat[1] > 0 else 0
        for stat in treatment_stats
    }
    treatment_commission = {
        str(stat[0]): {
            'total': float(stat[4] or 0),
            'fixed_rate': float(stat[5] or 0)
        }
        for stat in treatment_stats
    }
    
    # Average commission per referral
    avg_commission = float(total_commissions) / completed if completed > 0 else 0
    
    # Monthly growth rate calculation
    last_month = start_date - timedelta(days=30)
    current_month_referrals = total_referrals
    last_month_referrals = Referral.query.filter(
        Referral.created_at.between(last_month, start_date)
    ).count()
    
    monthly_growth_rate = (
        ((current_month_referrals - last_month_referrals) / last_month_referrals * 100)
        if last_month_referrals > 0 else 0
    )
    
    return {
        'total_referrals': total_referrals,
        'total_commissions': float(total_commissions),
        'avg_commission': round(float(avg_commission), 2),
        'status_counts': status_counts,
        'conversion_rate': round(conversion_rate, 2),
        'treatment_distribution': treatment_distribution,
        'treatment_success_rate': {k: round(v, 2) for k, v in treatment_success_rate.items()},
        'commission_distribution': commission_distribution,
        'treatment_commission': treatment_commission,
        'monthly_growth_rate': round(monthly_growth_rate, 2)
    }

def get_top_affiliates(limit=5):
    """Get top performing affiliates based on completed referrals and earnings"""
    return db.session.query(
        Affiliate,
        func.count(Referral.id).label('total_referrals'),
        func.sum(case((Referral.status == 'completed', 1), else_=0)).label('completed_referrals')
    ).outerjoin(
        Referral, Affiliate.id == Referral.affiliate_id
    ).group_by(Affiliate.id).order_by(
        func.sum(Referral.commission_amount).desc()
    ).limit(limit).all()
