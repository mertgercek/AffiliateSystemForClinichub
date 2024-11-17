from app import create_app, db
from models import User, Affiliate, Treatment, TreatmentGroup, Referral, Treatment_Status
from datetime import datetime, timedelta
import random
from faker import Faker
from countries import COUNTRIES

fake = Faker()

def create_treatment_groups():
    """Create sample treatment groups"""
    groups = [
        {
            'name': 'Hair Transplant',
            'description': 'Advanced hair restoration treatments',
            'commission_amount': 500.00
        },
        {
            'name': 'Dental Treatments',
            'description': 'Comprehensive dental procedures',
            'commission_amount': 300.00
        },
        {
            'name': 'Plastic Surgery',
            'description': 'Cosmetic and reconstructive procedures',
            'commission_amount': 1000.00
        },
        {
            'name': 'Eye Surgery',
            'description': 'Advanced ophthalmological procedures',
            'commission_amount': 400.00
        }
    ]
    
    created_groups = []
    for group in groups:
        treatment_group = TreatmentGroup(
            name=group['name'],
            description=group['description'],
            commission_amount=group['commission_amount']
        )
        db.session.add(treatment_group)
        created_groups.append(treatment_group)
    
    db.session.commit()
    return created_groups

def create_treatments(groups):
    """Create sample treatments for each group"""
    treatments_data = {
        'Hair Transplant': [
            'FUE Hair Transplant',
            'DHI Hair Transplant',
            'Sapphire FUE Treatment',
            'Beard Transplant'
        ],
        'Dental Treatments': [
            'All-on-4 Dental Implants',
            'Dental Veneers',
            'Full Mouth Rehabilitation',
            'Dental Crowns'
        ],
        'Plastic Surgery': [
            'Rhinoplasty',
            'Breast Augmentation',
            'Liposuction',
            'Face Lift'
        ],
        'Eye Surgery': [
            'LASIK Surgery',
            'Cataract Surgery',
            'PRK Treatment',
            'ICL Surgery'
        ]
    }
    
    created_treatments = []
    for group in groups:
        treatments = treatments_data.get(group.name, [])
        for treatment_name in treatments:
            treatment = Treatment(
                name=treatment_name,
                description=fake.paragraph(),
                group_id=group.id,
                active=True,
                average_duration=random.randint(30, 180)
            )
            db.session.add(treatment)
            created_treatments.append(treatment)
    
    db.session.commit()
    return created_treatments

def create_affiliates(num_affiliates=10):
    """Create sample affiliates with users"""
    affiliates = []
    for i in range(num_affiliates):
        # Create user
        user = User()
        user.username = fake.user_name()
        user.email = fake.email()
        user.set_password('password123')
        user.role = 'affiliate'
        user.email_verified = True
        db.session.add(user)
        
        # Create affiliate
        affiliate = Affiliate()
        affiliate.user = user
        affiliate.slug = f"aff{i+1}"
        affiliate.approved = True
        
        # Random country selection
        country = random.choice(COUNTRIES)
        affiliate.country = country['code']
        affiliate.city = fake.city()
        
        # Random coordinates within reasonable bounds
        affiliate.latitude = fake.latitude()
        affiliate.longitude = fake.longitude()
        affiliate.ip_address = fake.ipv4()
        
        db.session.add(affiliate)
        affiliates.append(affiliate)
    
    db.session.commit()
    return affiliates

def create_referrals(affiliates, treatments, num_referrals_per_affiliate=20):
    """Create sample referrals for each affiliate"""
    statuses = ['new', 'in-progress', 'completed']
    
    for affiliate in affiliates:
        for _ in range(num_referrals_per_affiliate):
            # Select random treatment
            treatment = random.choice(treatments)
            
            # Generate random dates within last 6 months
            created_at = datetime.utcnow() - timedelta(days=random.randint(0, 180))
            
            # Random status with weighted probability
            status = random.choices(
                statuses, 
                weights=[0.2, 0.3, 0.5]
            )[0]
            
            # Random country selection
            country = random.choice(COUNTRIES)
            
            referral = Referral(
                affiliate_id=affiliate.id,
                treatment_id=treatment.id,
                name=fake.first_name(),
                surname=fake.last_name(),
                email=fake.email(),
                phone=f"{country['dial_code']}{fake.msisdn()[4:]}",
                status=status,
                created_at=created_at,
                country=country['code'],
                city=fake.city(),
                latitude=fake.latitude(),
                longitude=fake.longitude(),
                ip_address=fake.ipv4()
            )
            
            # Add commission for completed referrals
            if status == 'completed':
                referral.commission_amount = float(treatment.group.commission_amount)
                affiliate.total_earnings = float(affiliate.total_earnings or 0) + referral.commission_amount
            
            db.session.add(referral)
            
            # Create treatment status for completed referrals
            if status == 'completed':
                treatment_status = Treatment_Status(
                    referral=referral,
                    start_date=created_at + timedelta(days=random.randint(1, 7)),
                    end_date=created_at + timedelta(days=random.randint(8, 30)),
                    notes=fake.paragraph(),
                    outcome='success'
                )
                db.session.add(treatment_status)
    
    db.session.commit()

def main():
    app = create_app()
    with app.app_context():
        print("Creating treatment groups...")
        groups = create_treatment_groups()
        
        print("Creating treatments...")
        treatments = create_treatments(groups)
        
        print("Creating affiliates...")
        affiliates = create_affiliates(10)  # Create 10 affiliates
        
        print("Creating referrals...")
        create_referrals(affiliates, treatments, 20)  # 20 referrals per affiliate
        
        print("Database populated successfully!")

if __name__ == '__main__':
    main() 