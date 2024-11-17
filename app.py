import os
from flask import Flask, redirect, url_for
from dotenv import load_dotenv
from flask_login import current_user
from sqlalchemy import text
from extensions import db, login_manager, toolbar

# Load environment variables first
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "default-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config['MANDRILL_API_KEY'] = os.environ.get('MANDRILL_API_KEY')
    
    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    toolbar.init_app(app)

    # Move user loader callback inside create_app
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

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
        from models import User
        
        # Test database connection
        try:
            db.session.execute(text('SELECT 1'))
            print("Database connection successful!")
        except Exception as e:
            print("Database connection failed:", e)
            return app
        
        # Create database tables
        db.create_all()

        # Create admin user if not exists
        admin = User.query.filter_by(email='admin@clinichub.com').first()
        if not admin:
            admin = User()
            admin.username = 'admin'
            admin.email = 'admin@clinichub.com'
            admin.role = 'admin'
            admin.set_password('admin123')
            admin.email_verified = True
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
