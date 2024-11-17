from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db
from decimal import Decimal, InvalidOperation
import logging
from sqlalchemy.exc import SQLAlchemyError
import secrets

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='affiliate')
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    affiliate = db.relationship('Affiliate', back_populates='user', uselist=False, cascade='all, delete-orphan')
    api_keys = db.relationship('APIKey', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self, name):
        """Generate a new API key for the user"""
        api_key = APIKey(
            user=self,
            name=name,
            key=secrets.token_urlsafe(32)
        )
        db.session.add(api_key)
        db.session.commit()
        return api_key

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'key': self.key,
            'created_at': self.created_at.isoformat(),
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'is_active': self.is_active
        }

class Affiliate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    slug = db.Column(db.String(20), unique=True)
    approved = db.Column(db.Boolean, default=False)
    commission_rate = db.Column(db.Numeric(5, 2), default=0.00)
    total_earnings = db.Column(db.Numeric(10, 2), default=0.00)
    
    user = db.relationship('User', back_populates='affiliate')
    referrals = db.relationship('Referral', backref='affiliate', lazy=True)

    def calculate_commission(self, treatment):
        """Calculate commission amount based on treatment group's fixed commission"""
        logging.info(f"Starting commission calculation for treatment {treatment.id if treatment else 'None'}")
        
        try:
            if not treatment:
                logging.error("Treatment object is missing")
                return 0.00
                
            if not treatment.group:
                logging.error(f"Treatment {treatment.id} has no associated group")
                return 0.00
                
            if not treatment.group.commission_amount:
                logging.error(f"Treatment group {treatment.group.id} has no commission amount set")
                return 0.00
                
            if float(treatment.group.commission_amount) <= 0:
                logging.error(f"Treatment group {treatment.group.id} has invalid commission amount: {treatment.group.commission_amount}")
                return 0.00
                
            commission = float(treatment.group.commission_amount)
            logging.info(f"Calculated commission amount: ${commission} for treatment {treatment.id}")
            return commission
            
        except (AttributeError, TypeError) as e:
            logging.error(f"Error accessing treatment attributes: {str(e)}")
            return 0.00
        except Exception as e:
            logging.error(f"Unexpected error calculating commission: {str(e)}")
            return 0.00

    def update_earnings(self):
        """Update total earnings based on completed referrals"""
        logging.info(f"Starting earnings update for affiliate {self.id}")
        
        try:
            total = Decimal('0.00')
            for referral in self.referrals:
                if referral.status == 'completed' and referral.commission_amount:
                    try:
                        commission = Decimal(str(referral.commission_amount))
                        if commission > 0:
                            total += commission
                            logging.info(f"Added commission ${commission} from referral {referral.id}")
                    except (InvalidOperation, TypeError) as e:
                        logging.error(f"Error processing commission amount for referral {referral.id}: {str(e)}")
                        continue
                        
            self.total_earnings = total
            logging.info(f"Updated total earnings to ${total} for affiliate {self.id}")
            db.session.commit()
            
        except SQLAlchemyError as e:
            logging.error(f"Database error updating earnings: {str(e)}")
            db.session.rollback()
            raise
        except Exception as e:
            logging.error(f"Unexpected error updating earnings: {str(e)}")
            db.session.rollback()
            raise

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.user.username,
            'commission_rate': float(self.commission_rate or 0),
            'total_earnings': float(self.total_earnings or 0)
        }

class TreatmentGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    commission_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    treatments = db.relationship('Treatment', backref='group', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'commission_amount': float(self.commission_amount or 0)
        }

class Treatment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    group_id = db.Column(db.Integer, db.ForeignKey('treatment_group.id'))
    referrals = db.relationship('Referral', backref='treatment', lazy=True)
    average_duration = db.Column(db.Integer)  # in days

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'active': self.active,
            'group': self.group.to_dict() if self.group else None
        }

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    affiliate_id = db.Column(db.Integer, db.ForeignKey('affiliate.id'), nullable=False)
    treatment_id = db.Column(db.Integer, db.ForeignKey('treatment.id'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    surname = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='new')
    commission_amount = db.Column(db.Numeric(10, 2), default=0.00)
    treatment_value = db.Column(db.Numeric(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    treatment_status = db.relationship('Treatment_Status', backref='referral', uselist=False)

    def validate_for_completion(self):
        """Validate if referral can be marked as completed"""
        if not self.treatment:
            logging.error(f"Referral {self.id} has no associated treatment")
            return False, "Missing treatment information"
            
        if not self.treatment.group:
            logging.error(f"Treatment {self.treatment.id} has no associated group")
            return False, "Treatment has no group assigned"
            
        if not self.treatment.group.commission_amount:
            logging.error(f"Treatment group {self.treatment.group.id} has no commission amount set")
            return False, "Treatment group has no commission amount"
            
        if float(self.treatment.group.commission_amount) <= 0:
            logging.error(f"Invalid commission amount ${self.treatment.group.commission_amount}")
            return False, "Invalid commission amount"
            
        if not self.affiliate:
            logging.error(f"Referral {self.id} has no associated affiliate")
            return False, "Missing affiliate information"
            
        return True, None

    def calculate_and_update_commission(self):
        """Calculate and update commission amount based on treatment's group commission"""
        logging.info(f"Starting commission calculation for referral {self.id}")
        
        try:
            # Pre-validate completion requirements
            is_valid, error_message = self.validate_for_completion()
            if not is_valid:
                return False, error_message

            # Verify referral status
            if self.status != 'completed':
                logging.info(f"Referral {self.id} is not completed, status: {self.status}")
                return False, "Referral is not completed"

            # Start transaction
            db.session.begin_nested()
            
            try:
                # Calculate commission
                commission = self.affiliate.calculate_commission(self.treatment)
                logging.info(f"Calculated commission: ${commission}")
                
                if commission <= 0:
                    db.session.rollback()
                    logging.warning(f"Zero or negative commission calculated for referral {self.id}")
                    return False, "Invalid commission amount calculated"

                # Update commission amount
                self.commission_amount = Decimal(str(commission))
                logging.info(f"Setting commission amount to ${commission}")
                
                # Update affiliate's total earnings
                logging.info(f"Updating earnings for affiliate {self.affiliate.id}")
                self.affiliate.update_earnings()
                
                # Commit transaction
                db.session.commit()
                logging.info(f"Successfully updated commission and earnings for referral {self.id}")
                return True, None
                
            except (InvalidOperation, TypeError) as e:
                db.session.rollback()
                logging.error(f"Error converting commission amount: {str(e)}")
                return False, "Invalid commission amount format"
                
            except SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Database error updating commission: {str(e)}")
                return False, "Database error occurred"
                
        except Exception as e:
            if db.session.is_active:
                db.session.rollback()
            logging.error(f"Unexpected error in commission calculation: {str(e)}")
            return False, "Unexpected error occurred"

    def to_dict(self):
        """Convert referral to dictionary for JSON serialization"""
        try:
            return {
                'id': self.id,
                'name': self.name,
                'surname': self.surname,
                'email': self.email,
                'phone': self.phone,
                'status': self.status,
                'commission_amount': float(self.commission_amount or 0),
                'treatment_value': float(self.treatment_value or 0),
                'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'treatment': self.treatment.to_dict() if self.treatment else None,
                'affiliate': {
                    'id': self.affiliate.id,
                    'username': self.affiliate.user.username
                } if self.affiliate else None
            }
        except Exception as e:
            logging.error(f"Error serializing referral {self.id}: {str(e)}")
            return None

class Treatment_Status(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(db.Integer, db.ForeignKey('referral.id'), nullable=False)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    outcome = db.Column(db.String(50))  # success, partial, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'start_date': self.start_date.strftime('%Y-%m-%d %H:%M:%S') if self.start_date else None,
            'end_date': self.end_date.strftime('%Y-%m-%d %H:%M:%S') if self.end_date else None,
            'notes': self.notes,
            'outcome': self.outcome
        }