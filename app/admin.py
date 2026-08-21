from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import User, Task, TaskSubmission, Referral, Withdrawal, AirtimePurchase


admin = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required():
    return current_user.is_authenticated and current_user.is_admin


@admin.before_request
def protect_admin():

    if not current_user.is_authenticated:
        return redirect(url_for("main.login"))

    if not current_user.is_admin:
        flash("Administrator access required.", "error")
        return redirect(url_for("main.dashboard"))


@admin.route("/")
def dashboard():

    users = User.query.order_by(
        User.created_at.desc()
    ).all()

    tasks = Task.query.order_by(
        Task.created_at.desc()
    ).all()

    # Admin only needs to see submissions waiting for review.
    # Approved/rejected submissions remain in the database
    # so workers can still see their submission history.
    submissions = TaskSubmission.query.filter_by(
        status="pending"
    ).order_by(
        TaskSubmission.created_at.desc()
    ).all()

    withdrawals = Withdrawal.query.order_by(
        Withdrawal.created_at.desc()
    ).all()

    airtime_requests = AirtimePurchase.query.order_by(
        AirtimePurchase.created_at.desc()
    ).all()

    return render_template(
        "admin/dashboard.html",
        users=users,
        tasks=tasks,
        submissions=submissions,
        withdrawals=withdrawals,
        airtime_requests=airtime_requests
    )


@admin.route("/task/create", methods=["GET", "POST"])
def create_task():

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        task_link = request.form.get("task_link", "").strip()
        reward_text = request.form.get("reward", "").strip()
        workers_text = request.form.get("workers_needed", "").strip()

        try:
            reward = float(reward_text)
        except (ValueError, TypeError):
            flash("Enter a valid task reward.", "error")
            return redirect(url_for("admin.create_task"))

        try:
            workers_needed = int(workers_text)
        except (ValueError, TypeError):
            flash("Enter a valid number of workers.", "error")
            return redirect(url_for("admin.create_task"))

        if not title or not description or not task_link:
            flash("Complete all task fields.", "error")
            return redirect(url_for("admin.create_task"))

        if not (
            task_link.startswith("http://")
            or task_link.startswith("https://")
        ):
            flash(
                "Task link must begin with http:// or https://",
                "error"
            )
            return redirect(url_for("admin.create_task"))

        if reward <= 0:
            flash("Task reward must be greater than zero.", "error")
            return redirect(url_for("admin.create_task"))

        if workers_needed <= 0:
            flash("Workers needed must be at least 1.", "error")
            return redirect(url_for("admin.create_task"))

        task = Task(
            title=title,
            description=description,
            task_link=task_link,
            reward=reward,
            workers_needed=workers_needed,
            workers_remaining=workers_needed,
            active=True
        )

        db.session.add(task)
        db.session.commit()

        flash("Task created successfully.", "success")

        return redirect(url_for("admin.dashboard"))

    return render_template("admin/create_task.html")


@admin.route("/task/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):

    task = Task.query.get_or_404(task_id)

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        task_link = request.form.get("task_link", "").strip()
        reward_text = request.form.get("reward", "").strip()
        workers_text = request.form.get("workers_needed", "").strip()

        try:
            reward = float(reward_text)
            workers_needed = int(workers_text)
        except (ValueError, TypeError):
            flash("Enter valid reward and worker values.", "error")
            return redirect(url_for("admin.edit_task", task_id=task.id))

        if not title or not description or not task_link:
            flash("Complete all task fields.", "error")
            return redirect(url_for("admin.edit_task", task_id=task.id))

        if not task_link.startswith(("http://", "https://")):
            flash(
                "Task link must begin with http:// or https://",
                "error"
            )
            return redirect(url_for("admin.edit_task", task_id=task.id))

        if reward <= 0 or workers_needed <= 0:
            flash("Reward and workers must be greater than zero.", "error")
            return redirect(url_for("admin.edit_task", task_id=task.id))

        used_workers = task.workers_needed - task.workers_remaining

        task.title = title
        task.description = description
        task.task_link = task_link
        task.reward = reward
        task.workers_needed = max(workers_needed, used_workers)
        task.workers_remaining = task.workers_needed - used_workers

        if task.workers_remaining > 0:
            task.active = True
        else:
            task.workers_remaining = 0
            task.active = False

        db.session.commit()

        flash("Task updated successfully.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/edit_task.html", task=task)


@admin.route("/task/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):

    task = Task.query.get_or_404(task_id)

    TaskSubmission.query.filter_by(task_id=task.id).delete(
        synchronize_session=False
    )

    db.session.delete(task)
    db.session.commit()

    flash("Task deleted successfully.", "success")

    return redirect(url_for("admin.dashboard"))


@admin.route("/task/<int:task_id>/toggle")
def toggle_task(task_id):

    task = Task.query.get_or_404(task_id)

    task.active = not task.active

    db.session.commit()

    flash("Task status updated.", "success")

    return redirect(url_for("admin.dashboard"))


@admin.route("/submission/<int:submission_id>/approve")
def approve_submission(submission_id):

    submission = TaskSubmission.query.get_or_404(submission_id)

    if submission.status != "pending":
        flash("This submission has already been processed.", "error")
        return redirect(url_for("admin.dashboard"))

    submission.status = "approved"

    user = submission.user
    user.task_balance = (user.task_balance or 0) + submission.task.reward

    # Count approved tasks for referral qualification.
    referral = Referral.query.filter_by(
        referred_id=user.id
    ).first()

    if referral:
        referral.tasks_completed = (
            referral.tasks_completed or 0
        ) + 1

        # Referral reward is ₦50 after 2 approved tasks.
        if (
            referral.tasks_completed >= 2
            and not referral.reward_paid
        ):
            referrer = referral.referrer

            referrer.referral_balance = (
                referrer.referral_balance or 0
            ) + 50

            referral.reward_paid = True

    db.session.commit()

    flash(
        f"Submission approved. ₦{submission.task.reward:,.2f} added to user balance.",
        "success"
    )

    return redirect(url_for("admin.dashboard"))


@admin.route("/submission/<int:submission_id>/reject", methods=["POST"])
def reject_submission(submission_id):

    submission = TaskSubmission.query.get_or_404(submission_id)

    if submission.status != "pending":
        flash("This submission has already been processed.", "error")
        return redirect(url_for("admin.dashboard"))

    submission.status = "rejected"
    submission.rejection_reason = request.form.get(
        "reason",
        "Submission was not approved."
    ).strip()

    # Release the worker slot because this submission was rejected.
    task = submission.task
    task.workers_remaining = min(
        task.workers_remaining + 1,
        task.workers_needed
    )

    if task.workers_remaining > 0:
        task.active = True

    db.session.commit()

    flash("Submission rejected.", "success")

    return redirect(url_for("admin.dashboard"))


@admin.route("/withdrawal/<int:withdrawal_id>/approve")
def approve_withdrawal(withdrawal_id):

    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)

    if withdrawal.status != "pending":
        flash("This withdrawal has already been processed.", "error")
        return redirect(url_for("admin.dashboard"))

    withdrawal.status = "approved"

    db.session.commit()

    flash("Withdrawal approved.", "success")

    return redirect(url_for("admin.dashboard"))


@admin.route("/withdrawal/<int:withdrawal_id>/reject", methods=["POST"])
def reject_withdrawal(withdrawal_id):

    withdrawal = Withdrawal.query.get_or_404(withdrawal_id)

    if withdrawal.status != "pending":
        flash("This withdrawal has already been processed.", "error")
        return redirect(url_for("admin.dashboard"))

    withdrawal.status = "rejected"

    withdrawal.rejection_reason = request.form.get(
        "reason",
        "Withdrawal rejected."
    ).strip()

    # Return the reserved money to the correct balance.
    if withdrawal.balance_type == "task":
        withdrawal.user.task_balance += withdrawal.amount
    else:
        withdrawal.user.referral_balance += withdrawal.amount

    db.session.commit()

    flash("Withdrawal rejected and balance returned.", "success")

    return redirect(url_for("admin.dashboard"))


@admin.route("/airtime/<int:purchase_id>/approve")
def approve_airtime(purchase_id):

    purchase = AirtimePurchase.query.get_or_404(purchase_id)

    if purchase.status != "pending":
        flash(
            "This airtime request has already been processed.",
            "error"
        )
        return redirect(url_for("admin.dashboard"))

    purchase.status = "approved"

    db.session.commit()

    flash(
        f"Airtime request for ₦{purchase.amount:,.2f} approved.",
        "success"
    )

    return redirect(url_for("admin.dashboard"))


@admin.route(
    "/airtime/<int:purchase_id>/reject",
    methods=["POST"]
)
def reject_airtime(purchase_id):

    purchase = AirtimePurchase.query.get_or_404(purchase_id)

    if purchase.status != "pending":
        flash(
            "This airtime request has already been processed.",
            "error"
        )
        return redirect(url_for("admin.dashboard"))

    purchase.status = "rejected"

    purchase.rejection_reason = request.form.get(
        "reason",
        "Airtime request rejected."
    ).strip()

    # Return the reserved amount to the user's balance.
    purchase.user.task_balance = (
        purchase.user.task_balance or 0
    ) + purchase.amount

    db.session.commit()

    flash(
        "Airtime request rejected and balance returned.",
        "success"
    )

    return redirect(url_for("admin.dashboard"))
