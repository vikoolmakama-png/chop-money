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

        # Add new columns to existing databases when necessary.
        # db.create_all() does not modify existing tables.
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)

        if "task_submission" in inspector.get_table_names():
            columns = {
                column["name"]
                for column in inspector.get_columns("task_submission")
            }

            if "screenshot_data" not in columns:
                if db.engine.dialect.name == "sqlite":
                    db.session.execute(
                        text(
                            "ALTER TABLE task_submission "
                            "ADD COLUMN screenshot_data BLOB"
                        )
                    )
                elif db.engine.dialect.name == "postgresql":
                    db.session.execute(
                        text(
                            "ALTER TABLE task_submission "
                            "ADD COLUMN screenshot_data BYTEA"
                        )
                    )

                db.session.commit()

        # Add screenshot_url to existing databases when necessary.
        if "task_submission" in inspector.get_table_names():
            columns = {
                column["name"]
                for column in inspector.get_columns("task_submission")
            }

            if "screenshot_url" not in columns:
                db.session.execute(
                    text(
                        "ALTER TABLE task_submission "
                        "ADD COLUMN screenshot_url VARCHAR(1000)"
                    )
                )
                db.session.commit()

        admin_username = "Vikool"
        admin_email = "vikool@chopmoney.com"
        admin_password = "Vikool@4040"

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
