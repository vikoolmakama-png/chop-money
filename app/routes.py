from urllib.parse import urlparse
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from app import db
from app.models import User, Task, TaskSubmission, Referral, Withdrawal, AirtimePurchase, AirtimePurchase, Deposit


main = Blueprint("main", __name__)


TASK_MIN_WITHDRAWAL = 350
REFERRAL_REWARD = 60


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


@main.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():

    if request.method == "POST":

        sender_name = request.form.get(
            "sender_name", ""
        ).strip()

        sender_bank = request.form.get(
            "sender_bank", ""
        ).strip()

        amount_text = request.form.get(
            "amount", ""
        ).strip()

        reference = request.form.get(
            "reference", ""
        ).strip()

        if not sender_name:
            flash("Enter the sender's full name.", "error")
            return redirect(url_for("main.deposit"))

        if not sender_bank:
            flash("Enter the bank used to send the money.", "error")
            return redirect(url_for("main.deposit"))

        if not reference:
            flash("Enter the transaction reference.", "error")
            return redirect(url_for("main.deposit"))

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            flash("Enter a valid deposit amount.", "error")
            return redirect(url_for("main.deposit"))

        if amount < 200:
            flash("Minimum deposit is ₦200.", "error")
            return redirect(url_for("main.deposit"))

        deposit = Deposit(
            user_id=current_user.id,
            amount=amount,
            sender_name=sender_name,
            sender_bank=sender_bank,
            reference=reference,
            status="pending"
        )

        db.session.add(deposit)
        db.session.commit()

        flash(
            "Deposit submitted successfully. It is waiting for admin verification.",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    return render_template("deposit.html")


@main.route("/create-task", methods=["GET", "POST"])
@login_required
def create_task():

    TASK_PRICES = {
        "Telegram Bot": {"reward": 30, "fee": 10},
        "Share post": {"reward": 15, "fee": 10},
        "Sponsor post": {"reward": 25, "fee": 10},
        "X followers": {"reward": 10, "fee": 4},
        "Spotify": {"reward": 7, "fee": 5},
        "WhatsApp Group / Telegram": {"reward": 8, "fee": 4},
        "Custom Task": {"reward": 60, "fee": 25},
        "App Install and Register": {"reward": 70, "fee": 30},
        "YouTube Subscribers": {"reward": 10, "fee": 7},
        "Facebook Followers": {"reward": 8, "fee": 4},
        "Website Signups": {"reward": 20, "fee": 10},
        "Instagram Followers": {"reward": 7, "fee": 5},
        "TikTok Followers": {"reward": 7, "fee": 5},
        "Facebook, TikTok, Instagram and YouTube Likes": {"reward": 5, "fee": 5},
    }

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        task_link = request.form.get("task_link", "").strip()
        task_type = request.form.get("task_type", "").strip()
        workers_text = request.form.get("workers_needed", "").strip()

        if task_type not in TASK_PRICES:
            flash("Please select a valid task type.", "error")
            return redirect(url_for("main.create_task"))

        try:
            workers_needed = int(workers_text)
        except (ValueError, TypeError):
            flash("Enter a valid number of workers.", "error")
            return redirect(url_for("main.create_task"))

        if not title or not description or not task_link:
            flash("Complete all task fields.", "error")
            return redirect(url_for("main.create_task"))

        if not task_link.startswith(("http://", "https://")):
            flash("Task link must begin with http:// or https://", "error")
            return redirect(url_for("main.create_task"))

        if workers_needed < 5:
            flash("You must create a task for at least 5 workers.", "error")
            return redirect(url_for("main.create_task"))

        price = TASK_PRICES[task_type]

        # Amount charged to the task creator per worker.
        # The fee is included in this amount but is not shown
        # separately on the create-task page.
        reward = float(price["reward"])
        website_fee = float(price["fee"])

        amount_per_worker = reward + website_fee
        total_cost = amount_per_worker * workers_needed

        wallet = current_user.wallet_balance or 0

        if wallet < total_cost:
            flash(
                f"Insufficient wallet balance. You need ₦{total_cost:,.2f}.",
                "error"
            )
            return redirect(url_for("main.create_task"))

        task = Task(
            owner_id=current_user.id,
            title=title,
            description=description,
            task_link=task_link,
            reward=reward,
            task_type=task_type,
            total_cost=total_cost,
            website_fee=website_fee,
            workers_needed=workers_needed,
            workers_remaining=workers_needed,
            active=True
        )

        current_user.wallet_balance -= total_cost

        db.session.add(task)
        db.session.commit()

        flash(
            f"Task created successfully. ₦{total_cost:,.2f} deducted from your wallet.",
            "success"
        )

        return redirect(url_for("main.dashboard"))

    return render_template("create_task.html")
@main.route("/")
def home():
    return render_template("home.html")


@main.route("/register", methods=["GET", "POST"])
@main.route("/register/<referral_code>", methods=["GET", "POST"])
def register(referral_code=None):

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    referral_code = (
        referral_code
        or request.args.get("ref", "")
    ).strip().upper()

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


@main.route("/submission/<int:submission_id>/screenshot")
@login_required
def submission_screenshot(submission_id):
    from io import BytesIO
    from flask import send_file, abort

    submission = db.session.get(TaskSubmission, submission_id)

    if not submission or not submission.screenshot_data:
        abort(404)

    if (
        submission.user_id != current_user.id
        and not current_user.is_admin
    ):
        abort(403)

    filename = submission.screenshot_filename or "screenshot.jpg"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"

    mime_types = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }

    return send_file(
        BytesIO(submission.screenshot_data),
        mimetype=mime_types.get(extension, "image/jpeg"),
        download_name=filename
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

    # Keep tasks visible while a submission is pending.
    # Remove them from Available Tasks after approval or rejection.
    tasks = Task.query.filter(
        Task.active.is_(True),
        ~Task.submissions.any(
            db.and_(
                TaskSubmission.user_id == current_user.id,
                TaskSubmission.status.in_(["pending", "approved"])
            )
        )
    ).order_by(
        Task.created_at.desc()
    ).all()

    submissions = TaskSubmission.query.filter_by(
        user_id=current_user.id,
        status="pending"
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

        screenshot = request.files.get("screenshot")

        if not screenshot or not screenshot.filename:
            flash("Please upload a screenshot as proof of task completion.", "error")
            return redirect(
                url_for("main.task_detail", task_id=task.id)
            )

        allowed_extensions = {"png", "jpg", "jpeg", "webp"}
        original_name = secure_filename(screenshot.filename)
        extension = (
            original_name.rsplit(".", 1)[1].lower()
            if "." in original_name
            else ""
        )

        if extension not in allowed_extensions:
            flash(
                "Screenshot must be PNG, JPG, JPEG, or WEBP.",
                "error"
            )
            return redirect(
                url_for("main.task_detail", task_id=task.id)
            )

        upload_dir = os.path.join(
            os.path.dirname(__file__),
            "static",
            "uploads",
            "submissions"
        )
        os.makedirs(upload_dir, exist_ok=True)

        screenshot_filename = (
            f"user_{current_user.id}_task_{task.id}_"
            f"{secrets.token_hex(8)}.{extension}"
        )

        screenshot_data = screenshot.read()

        if not screenshot_data:
            flash("The uploaded screenshot is empty.", "error")
            return redirect(
                url_for("main.task_detail", task_id=task.id)
            )


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
            existing.screenshot_filename = screenshot_filename
            existing.screenshot_data = screenshot_data
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
                screenshot_filename=screenshot_filename,
                screenshot_data=screenshot_data,
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

            if amount < 100:
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
                "Minimum airtime purchase is ₦100.",
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
            db.and_(
                TaskSubmission.user_id == current_user.id,
                TaskSubmission.status.in_(["pending", "approved"])
            )
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


@main.route("/my-tasks")
@login_required
def my_tasks():
    """Show tasks created by the current user and their submissions."""
    tasks = Task.query.filter_by(
        owner_id=current_user.id
    ).order_by(
        Task.created_at.desc()
    ).all()

    return render_template(
        "my_tasks.html",
        tasks=tasks
    )


@main.route("/my-tasks/<int:task_id>/submission/<int:submission_id>/review",
             methods=["POST"])
@login_required
def review_task_submission(task_id, submission_id):
    """Allow a task creator to approve or reject their own task submissions."""

    task = Task.query.get_or_404(task_id)

    # Security: only the task creator can review submissions.
    if task.owner_id != current_user.id:
        flash("You are not allowed to review this task.", "error")
        return redirect(url_for("main.my_tasks"))

    submission = TaskSubmission.query.filter_by(
        id=submission_id,
        task_id=task.id
    ).first_or_404()

    # Do not process an already-reviewed submission.
    if submission.status != "pending":
        flash("This submission has already been reviewed.", "error")
        return redirect(url_for("main.my_tasks"))

    action = request.form.get("action", "").strip().lower()

    if action == "approve":

        # Pay the worker only once, when the creator approves.
        worker = submission.user
        worker.task_balance = (worker.task_balance or 0) + task.reward

        submission.status = "approved"
        submission.rejection_reason = None

        # Referral reward:
        # The referrer earns ₦50 after the referred user gets
        # 2 approved task submissions.
        referral = Referral.query.filter_by(
            referred_id=worker.id
        ).first()

        if referral and not referral.reward_paid:
            approved_count = TaskSubmission.query.filter_by(
                user_id=worker.id,
                status="approved"
            ).count()

            referral.tasks_completed = approved_count

            if approved_count >= 2:
                referrer = referral.referrer
                referrer.referral_balance = (
                    referrer.referral_balance or 0
                ) + REFERRAL_REWARD

                referral.reward_paid = True

        db.session.commit()

        flash(
            f"Submission approved. ₦{task.reward:,.2f} has been added "
            f"to {worker.username}'s task balance.",
            "success"
        )

    elif action == "reject":

        reason = request.form.get("rejection_reason", "").strip()

        if not reason:
            flash(
                "Please provide a rejection reason.",
                "error"
            )
            return redirect(url_for("main.my_tasks"))

        submission.status = "rejected"
        submission.rejection_reason = reason

        db.session.commit()

        flash(
            "Submission rejected. The worker can see your reason and resubmit.",
            "success"
        )

    else:
        flash("Invalid review action.", "error")

    return redirect(url_for("main.my_tasks"))
