from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_debugtoolbar import DebugToolbarExtension

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
toolbar = DebugToolbarExtension()
