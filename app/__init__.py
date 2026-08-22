import os
import secrets

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes import main
    app.register_blueprint(main)

    from app.admin import admin
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()

        # Create/update the deployment admin from environment variables.
        # Credentials are never stored in the source code.
        admin_username = os.environ.get("ADMIN_USERNAME")
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if admin_username and admin_email and admin_password:
            admin_user = User.query.filter(
                (User.username == admin_username) |
                (User.email == admin_email)
            ).first()

            if admin_user is None:
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    referral_code="CHOP-" + secrets.token_hex(3).upper(),
                    is_admin=True
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
            else:
                admin_user.is_admin = True
                admin_user.set_password(admin_password)

            db.session.commit()

    return app
