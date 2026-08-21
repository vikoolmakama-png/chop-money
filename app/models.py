from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)

    task_balance = db.Column(db.Float, default=0)
    referral_balance = db.Column(db.Float, default=0)

    referral_code = db.Column(db.String(30), unique=True, nullable=False)

    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def total_balance(self):
        return (self.task_balance or 0) + (self.referral_balance or 0)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    # Link users open to perform the task
    task_link = db.Column(db.String(500), nullable=False)

    reward = db.Column(db.Float, nullable=False)

    workers_needed = db.Column(db.Integer, nullable=False, default=1)
    workers_remaining = db.Column(db.Integer, nullable=False, default=1)

    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaskSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)

    note = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(20), default="pending")
    rejection_reason = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="task_submissions")
    task = db.relationship("Task", backref="submissions")


class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    referrer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    referred_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    tasks_completed = db.Column(db.Integer, default=0)
    reward_paid = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    referrer = db.relationship(
        "User",
        foreign_keys=[referrer_id],
        backref="referrals"
    )

    referred = db.relationship(
        "User",
        foreign_keys=[referred_id]
    )


class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    balance_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    account_name = db.Column(db.String(150), nullable=False)

    status = db.Column(db.String(20), default="pending")
    rejection_reason = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="withdrawals")


class AirtimePurchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    network = db.Column(db.String(30), nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    status = db.Column(
        db.String(20),
        default="pending",
        nullable=False
    )

    rejection_reason = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user = db.relationship(
        "User",
        backref="airtime_purchases"
    )
