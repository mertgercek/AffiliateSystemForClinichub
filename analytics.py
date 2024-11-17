from datetime import datetime, timedelta
from sqlalchemy import func, case, extract, text, and_
from models import User, Referral, Treatment, Affiliate, Treatment_Status, TreatmentGroup
from extensions import db

def get_conversion_metrics(start_date=None, end_date=None):
    """Get conversion metrics and analytics data with optional date filtering"""
    from models import Referral, Treatment
    from sqlalchemy import func, case, extract
    from datetime import datetime
    
    # Base query
    query = Referral.query
    
    # Apply date filters if provided
    if start_date and end_date:
        query = query.filter(
            and_(
                Referral.created_at >= start_date,
                Referral.created_at <= end_date
            )
        )
    
    # Get total referrals
    total_referrals = query.count()
    
    # Get status counts with proper initialization
    status_counts = {
        'new': 0,
        'in-progress': 0,
        'completed': 0
    }
    
    # Update with actual counts
    status_query = db.session.query(
        Referral.status,
        func.count(Referral.id).label('count')
    ).filter(
        query.whereclause if query.whereclause is not None else True
    ).group_by(Referral.status).all()
    
    for status, count in status_query:
        status_counts[status] = count
    
    # Calculate total commission from completed referrals
    total_commission = db.session.query(
        func.sum(case(
            (Referral.status == 'completed', Referral.commission_amount),
            else_=0
        ))
    ).filter(
        query.whereclause if query.whereclause is not None else True
    ).scalar() or 0.0
    
    # Get monthly commission distribution
    current_year = datetime.utcnow().year
    commission_query = db.session.query(
        extract('month', Referral.created_at).label('month'),
        func.sum(case(
            (Referral.status == 'completed', Referral.commission_amount),
            else_=0
        )).label('commission')
    )
    
    if query.whereclause is not None:
        commission_query = commission_query.filter(query.whereclause)
    
    commission_by_month = commission_query.filter(
        extract('year', Referral.created_at) == current_year
    ).group_by('month').all()
    
    commission_distribution = {}
    for month, commission in commission_by_month:
        month_str = f"{current_year}-{int(month):02d}"
        commission_distribution[month_str] = float(commission or 0)
    
    # Calculate conversion rate
    completed_count = status_counts.get('completed', 0)
    conversion_rate = (completed_count / total_referrals * 100) if total_referrals > 0 else 0
    
    return {
        'total_referrals': total_referrals,
        'status_counts': status_counts,
        'total_commission': float(total_commission),
        'commission_distribution': commission_distribution,
        'conversion_rate': round(conversion_rate, 1)
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

def get_country_stats():
    """Get referral statistics by country"""
    from models import Referral
    from sqlalchemy import func, case
    
    country_stats = db.session.query(
        Referral.country,
        func.count(Referral.id).label('total_referrals'),
        func.count(case(
            (Referral.status == 'completed', 1),
            else_=None
        )).label('completed_referrals'),
        func.sum(case(
            (Referral.status == 'completed', Referral.commission_amount),
            else_=0
        )).label('total_commission')
    ).filter(
        Referral.country.isnot(None)
    ).group_by(
        Referral.country
    ).order_by(
        func.count(Referral.id).desc()
    ).all()
    
    return [{
        'country': stat.country,
        'total_referrals': stat.total_referrals,
        'completed_referrals': stat.completed_referrals,
        'completion_rate': (stat.completed_referrals / stat.total_referrals * 100) if stat.total_referrals > 0 else 0,
        'total_commission': float(stat.total_commission or 0)
    } for stat in country_stats]
