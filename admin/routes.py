from flask import render_template, redirect, url_for, request
from flask_login import current_user
from . import admin_bp
from .decorators import login_required_admin
from services import admin_service
from constants import SINTOMAS_DISPONIBLES


@admin_bp.route("/")
@login_required_admin
def index():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@login_required_admin
def dashboard():
    stats = admin_service.get_dashboard_stats()
    today_appts = admin_service.get_today_appointments()
    recent_appts = admin_service.get_recent_appointments(limit=5)
    return render_template("dashboard.html", stats=stats, today_appts=today_appts, recent_appts=recent_appts)


@admin_bp.route("/patients")
@login_required_admin
def patients():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip()
    pagination = admin_service.get_patients_paginated(page=page, per_page=20, search=search or None)
    stats = admin_service.get_dashboard_stats()
    return render_template("patients/list.html", pagination=pagination, search=search, stats=stats)


@admin_bp.route("/patients/<int:patient_id>")
@login_required_admin
def patient_detail(patient_id):
    detail = admin_service.get_patient_detail(patient_id)
    stats = admin_service.get_dashboard_stats()
    return render_template("patients/detail.html", **detail, stats=stats)


@admin_bp.route("/appointments")
@login_required_admin
def appointments():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "").strip() or None
    symptom = request.args.get("symptom", "").strip() or None
    search = request.args.get("q", "").strip() or None
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None

    pagination = admin_service.get_appointments_paginated(
        page=page, per_page=20, status=status,
        symptom=symptom, search=search, date_from=date_from, date_to=date_to,
    )
    stats = admin_service.get_dashboard_stats()

    from models.appointment import APPOINTMENT_STATUSES

    return render_template(
        "appointments/list.html",
        pagination=pagination, stats=stats,
        APPOINTMENT_STATUSES=APPOINTMENT_STATUSES, SYMPTOMS=SINTOMAS_DISPONIBLES,
        filters={"status": status, "symptom": symptom, "q": search,
                 "date_from": date_from, "date_to": date_to},
    )


@admin_bp.route("/appointments/calendar")
@login_required_admin
def calendar_view():
    from datetime import datetime
    year = request.args.get("year", datetime.utcnow().year, type=int)
    month = request.args.get("month", datetime.utcnow().month, type=int)

    appts = admin_service.get_calendar_appointments(year, month)
    stats = admin_service.get_dashboard_stats()

    # Build calendar grid data
    import calendar as cal
    cal_obj = cal.Calendar(firstweekday=0)
    weeks = cal_obj.monthdatescalendar(year, month)

    appt_by_day = {}
    for a in appts:
        day_key = a.scheduled_at.date()
        appt_by_day.setdefault(day_key, []).append(a)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_name = cal.month_name[month]

    return render_template(
        "appointments/calendar.html",
        stats=stats, weeks=weeks, appt_by_day=appt_by_day,
        year=year, month=month, month_name=month_name,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        current_date=datetime.utcnow().date(),
    )


@admin_bp.route("/stats")
@login_required_admin
def stats():
    dashboard_stats = admin_service.get_dashboard_stats()
    symptom_stats = admin_service.get_symptom_stats()
    monthly_data = admin_service.get_monthly_appointments(months=6)
    return render_template("stats.html", stats=dashboard_stats,
                           symptom_stats=symptom_stats, monthly_data=monthly_data)
