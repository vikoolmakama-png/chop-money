from urllib.parse import urlparse
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from app import db
from app.models import User, Task, TaskSubmission, Referral, Withdrawal, AirtimePurchase, AirtimePurchase


main = Blueprint("main", __name__)


TASK_MIN_WITHDRAWAL = 500
REFERRAL_REWARD = 50


def valid_url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def generate_referral_code():
    while True:
        code = "CHOP-" + secrets.token_hex(3).upper()
        if not User.query.filter_by(referral_code=code).first():
            return code


@main.route("/")
def home():
    return render_template("home.html")


@main.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    referral_code = request.args.get("ref", "").strip().upper()

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        referral_code = request.form.get(
            "referral_code",
            referral_code
        ).strip().upper()

        if not username or not email or not password:
            flash("Please complete all required fields.", "error")
            return redirect(url_for("main.register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("main.register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("main.register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("main.register"))

        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "error")
            return redirect(url_for("main.register"))

        referrer = None

        if referral_code:
            referrer = User.query.filter_by(
                referral_code=referral_code
            ).first()

            if not referrer:
                flash("Invalid referral code.", "error")
                return redirect(url_for("main.register"))

        user = User(
            username=username,
            email=email,
            referral_code=generate_referral_code()
        )

        user.set_password(password)

        db.session.add(user)
        db.session.flush()

        if referrer and referrer.id != user.id:
            referral = Referral(
                referrer_id=referrer.id,
                referred_id=user.id
            )
            db.session.add(referral)

        db.session.commit()

        login_user(user)

        flash("Account created successfully.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template(
        "register.html",
        referral_code=referral_code
    )


@main.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifier) |
            (User.email == identifier.lower())
        ).first()

        if not user or not user.check_password(password):
            flash("Invalid login details.", "error")
            return redirect(url_for("main.login"))

        login_user(user)

        if user.is_admin:
            return redirect(url_for("admin.dashboard"))

        return redirect(url_for("main.dashboard"))

    return render_template("login.html")


@main.route("/logout")
@login_required
def logout():

    logout_user()

    flash("You have been logged out.", "success")

    return redirect(url_for("main.home"))


@main.route("/dashboard")
@login_required
def dashboard():

    # A worker should only see tasks they have never submitted.
    # This includes rejected submissions: rejected tasks can be
    # resubmitted from the task/submission page, but must not return
    # to the Available Tasks list.
    tasks = Task.query.filter(
        Task.active.is_(True),
        ~Task.submissions.any(
            TaskSubmission.user_id == current_user.id
        )
    ).order_by(
        Task.created_at.desc()
    ).all()

    submissions = TaskSubmission.query.filter_by(
        user_id=current_user.id
    ).order_by(
        TaskSubmission.created_at.desc()
    ).limit(10).all()

    return render_template(
        "dashboard.html",
        tasks=tasks,
        submissions=submissions
    )


@main.route("/task/<int:task_id>", methods=["GET", "POST"])
@login_required
def task_detail(task_id):

    task = Task.query.get_or_404(task_id)

    if not task.active:
        flash("This task is no longer available.", "error")
        return redirect(url_for("main.dashboard"))

    existing = TaskSubmission.query.filter_by(
        user_id=current_user.id,
        task_id=task.id
    ).order_by(
        TaskSubmission.created_at.desc()
    ).first()

    if request.method == "POST":

        note = request.form.get("note", "").strip()

        if not note:
            flash("Please enter your completion note.", "error")
            return redirect(
                url_for("main.task_detail", task_id=task.id)
            )

        if existing and existing.status in ("pending", "approved"):
            flash("You have already submitted this task.", "error")
            return redirect(
                url_for("main.task_detail", task_id=task.id)
            )

        if existing and existing.status == "rejected":
            existing.note = note
            existing.status = "pending"
            existing.rejection_reason = None

            db.session.commit()

            flash(
                "Task resubmitted. Waiting for admin approval.",
                "success"
            )

        else:
            if task.workers_remaining <= 0:
                task.active = False
                db.session.commit()

                flash(
                    "This task has reached its worker limit.",
                    "error"
                )
                return redirect(url_for("main.dashboard"))

            submission = TaskSubmission(
                user_id=current_user.id,
                task_id=task.id,
                note=note,
                status="pending"
            )

            db.session.add(submission)

            task.workers_remaining -= 1

            if task.workers_remaining <= 0:
                task.workers_remaining = 0
                task.active = False

            db.session.commit()

            flash(
                "Task submitted. Waiting for admin approval.",
                "success"
            )

        return redirect(url_for("main.dashboard"))

    return render_template(
        "task.html",
        task=task,
        existing=existing
    )


@main.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():

    if request.method == "POST":

        balance_type = request.form.get("balance_type", "task")
        amount_text = request.form.get("amount", "").strip()

        bank_name = request.form.get("bank_name", "").strip()
        account_number = request.form.get("account_number", "").strip()
        account_name = request.form.get("account_name", "").strip()

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            flash("Enter a valid withdrawal amount.", "error")
            return redirect(url_for("main.withdraw"))

        if amount <= 0:
            flash("Withdrawal amount must be greater than zero.", "error")
            return redirect(url_for("main.withdraw"))

        if balance_type == "task":

            if amount < TASK_MIN_WITHDRAWAL:
                flash(
                    "Minimum task withdrawal is ₦500.",
                    "error"
                )
                return redirect(url_for("main.withdraw"))

            balance = current_user.task_balance or 0

        elif balance_type == "referral":

            balance = current_user.referral_balance or 0

            if amount < 500:
                flash(
                    "Minimum withdrawal is ₦500.",
                    "error"
                )
                return redirect(url_for("main.withdraw"))

        else:
            flash("Invalid balance type.", "error")
            return redirect(url_for("main.withdraw"))

        if amount > balance:
            flash(
                "Withdrawal amount is greater than your available balance.",
                "error"
            )
            return redirect(url_for("main.withdraw"))

        if not bank_name or not account_number or not account_name:
            flash(
                "Please provide your complete bank details.",
                "error"
            )
            return redirect(url_for("main.withdraw"))

        # Reserve/deduct the money immediately so the same balance
        # cannot be requested in multiple pending withdrawals.
        if balance_type == "task":
            current_user.task_balance -= amount
        else:
            current_user.referral_balance -= amount

        withdrawal = Withdrawal(
            user_id=current_user.id,
            balance_type=balance_type,
            amount=amount,
            bank_name=bank_name,
            account_number=account_number,
            account_name=account_name
        )

        db.session.add(withdrawal)
        db.session.commit()

        flash(
            "Withdrawal request submitted successfully.",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    withdrawal_history = Withdrawal.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Withdrawal.created_at.desc()
    ).all()

    return render_template(
        "withdraw.html",
        withdrawal_history=withdrawal_history
    )


@main.route("/referrals")
@login_required
def referrals():

    referral_list = Referral.query.filter_by(
        referrer_id=current_user.id
    ).order_by(
        Referral.created_at.desc()
    ).all()

    return render_template(
        "referrals.html",
        referrals=referral_list,
        reward=REFERRAL_REWARD
    )


AIRTIME_MINIMUM = 50


@main.route("/airtime", methods=["GET", "POST"])
@login_required
def airtime():

    if request.method == "POST":

        network = request.form.get("network", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        amount_text = request.form.get("amount", "").strip()

        allowed_networks = {
            "MTN",
            "Airtel",
            "Glo",
            "9mobile"
        }

        if network not in allowed_networks:
            flash("Please select a valid network.", "error")
            return redirect(url_for("main.airtime"))

        if not phone_number:
            flash("Please enter the phone number.", "error")
            return redirect(url_for("main.airtime"))

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            flash("Enter a valid airtime amount.", "error")
            return redirect(url_for("main.airtime"))

        if amount < AIRTIME_MINIMUM:
            flash(
                "Minimum airtime purchase is ₦50.",
                "error"
            )
            return redirect(url_for("main.airtime"))

        if amount <= 0:
            flash(
                "Airtime amount must be greater than zero.",
                "error"
            )
            return redirect(url_for("main.airtime"))

        if current_user.total_balance < amount:
            flash(
                "Insufficient balance for this airtime purchase.",
                "error"
            )
            return redirect(url_for("main.airtime"))

        # Reserve the money while the request is pending.
        #
        # We deduct from task balance first, then referral balance.
        remaining = amount

        task_balance = current_user.task_balance or 0

        task_deduction = min(task_balance, remaining)
        current_user.task_balance -= task_deduction
        remaining -= task_deduction

        if remaining > 0:
            current_user.referral_balance -= remaining

        purchase = AirtimePurchase(
            user_id=current_user.id,
            network=network,
            phone_number=phone_number,
            amount=amount,
            status="pending"
        )

        db.session.add(purchase)
        db.session.commit()

        flash(
            "Airtime request submitted. Waiting for admin approval.",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    airtime_history = AirtimePurchase.query.filter_by(
        user_id=current_user.id
    ).order_by(
        AirtimePurchase.created_at.desc()
    ).all()

    return render_template(
        "airtime.html",
        airtime_history=airtime_history
    )

@main.route("/tasks")
@login_required
def tasks_page():
    # A worker should only see tasks they have never submitted.
    # This includes rejected submissions: rejected tasks can be
    # resubmitted from the task/submission page, but must not return
    # to the Available Tasks list.
    tasks = Task.query.filter(
        Task.active.is_(True),
        ~Task.submissions.any(
            TaskSubmission.user_id == current_user.id
        )
    ).order_by(
        Task.created_at.desc()
    ).all()

    return render_template("tasks.html", tasks=tasks)


@main.route("/submissions")
@login_required
def submissions_page():
    submissions = TaskSubmission.query.filter_by(
        user_id=current_user.id
    ).order_by(
        TaskSubmission.created_at.desc()
    ).all()

    return render_template(
        "submissions.html",
        submissions=submissions
    )
