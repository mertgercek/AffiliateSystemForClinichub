import os
from flask import Flask, redirect, url_for, request, flash
from dotenv import load_dotenv
from flask_login import current_user
from sqlalchemy import text
from extensions import db, login_manager, toolbar
import requests
from filters import nl2br, flag
from flask_migrate import Migrate
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables first
load_dotenv()

def create_app():
    app = Flask(__name__, static_url_path='/static')
    
    # Ensure the static/images directory exists
    os.makedirs(os.path.join(app.static_folder, 'images'), exist_ok=True)
    
    # Simple error logging setup
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Set up file handler for errors only
    file_handler = RotatingFileHandler(
        'logs/error.log', 
        maxBytes=1024000,  # 1MB
        backupCount=5
    )
    
    # Only log errors
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s'
    ))
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.ERROR)
    
    # Add both filters
    app.jinja_env.filters['nl2br'] = nl2br
    app.jinja_env.filters['flag'] = flag
    
    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config['MANDRILL_API_KEY'] = os.environ.get('MANDRILL_API_KEY')
    app.config['RECAPTCHA_SITE_KEY'] = os.getenv('RECAPTCHA_SITE_KEY')
    app.config['RECAPTCHA_SECRET_KEY'] = os.getenv('RECAPTCHA_SECRET_KEY')
    
    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    toolbar.init_app(app)

    # Initialize Flask-Migrate
    migrate = Migrate(app, db)

    # Move user loader callback inside create_app
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return db.session.get(User, int(user_id))

    # Import blueprints
    from auth import bp as auth_bp
    from admin import bp as admin_bp
    from affiliate import bp as affiliate_bp
    from api import bp as api_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(affiliate_bp)
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Root route handler
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('affiliate.dashboard'))
        return redirect(url_for('auth.login'))

    # Initialize database
    with app.app_context():
        # Import models
        from models import User, Affiliate, Treatment, TreatmentGroup, Referral, Treatment_Status, Ticket, TicketResponse
        # Drop and recreate all tables
        # db.drop_all()
        db.create_all()
        
        # Check if admin user exists
        admin = User.query.filter_by(email='admin@clinichub.com').first()
        
        # Create admin user only if it doesn't exist
        if not admin:
            admin = User()
            admin.username = 'admin'
            admin.email = 'admin@clinichub.com'
            admin.role = 'admin'
            admin.set_password('admin123')
            admin.email_verified = True
            admin.last_seen = datetime.utcnow()
            db.session.add(admin)
            db.session.commit()
            app.logger.info('Admin user created successfully!')
        else:
            app.logger.info('Admin user already exists!')
            
    @app.before_request
    def before_request():
        if current_user.is_authenticated:
            current_user.last_seen = datetime.utcnow()
            db.session.commit()
            
    # Log all requests
    @app.after_request
    def after_request(response):
        if request.endpoint:
            app.logger.info(f'{request.remote_addr} - {request.method} {request.url} - {response.status_code}')
        return response

    @app.context_processor
    def utility_processor():
        def get_pending_affiliates_count():
            if current_user.is_authenticated and current_user.role == 'admin':
                from models import Affiliate
                return Affiliate.query.filter_by(approved=False).count()
            return 0
            
        return {
            'pending_affiliates_count': get_pending_affiliates_count()
        }

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
