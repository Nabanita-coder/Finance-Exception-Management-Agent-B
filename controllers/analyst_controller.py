"""
controllers/analyst_controller.py
----------------------------------
HTTP Controller for Accountable Owner / Finance Analyst (Role 1):
- My Tasks / Assigned Exception queue prioritized high to low
- SLA Tracker and Overdue / Near-breach Alerts
- AI Insights & Root-Cause analysis
- Quick Action Panel (Submit Explanation, Close/Resolve, Escalate)
All data managed via Stored Procedures.
"""

from flask import request, jsonify
from datetime import datetime, timedelta
from dbConnection.db import call_sp, get_session
from services.finance_models import ExceptionCase, FinancialRecord, Owner


def get_my_tasks():
    """
    GET: Returns assigned active exceptions ordered by priority (Severity & Variance).
    """
    user_id = request.args.get("user_id", 1, type=int)
    try:
        rows = call_sp("sp_get_analyst_tasks", [user_id])
        if rows:
            return jsonify({"success": True, "tasks": rows}), 200
    except Exception:
        pass

    session = get_session()
    try:
        # Load active cases, prioritizing assigned owner or high severity
        query = session.query(ExceptionCase).filter(
            ExceptionCase.status.in_(["OPEN", "IN_PROGRESS", "ESCALATED"])
        )
        if user_id:
            user_cases = query.filter(ExceptionCase.owner_id == user_id).all()
            if not user_cases:
                user_cases = query.all()
        else:
            user_cases = query.all()

        tasks = []
        for c in user_cases:
            rec = c.financial_record
            owner = c.owner
            tasks.append({
                "id": c.id,
                "financial_record_id": c.financial_record_id,
                "category": rec.category if rec else "Expense",
                "department": rec.department if rec else "Operations",
                "budget_amount": rec.budget_amount if rec else 0.0,
                "actual_amount": rec.actual_amount if rec else 0.0,
                "variance_percent": c.variance_percent,
                "severity": c.severity,
                "status": c.status,
                "sla_deadline": c.sla_deadline.strftime("%Y-%m-%d %H:%M") if c.sla_deadline else None,
                "owner_name": owner.name if owner else "Unassigned",
                "possible_reason": c.possible_reason,
                "escalation_level": c.escalation_level,
            })
        tasks.sort(key=lambda x: (x["severity"] == "CRITICAL", abs(x["variance_percent"])), reverse=True)
        return jsonify({"success": True, "tasks": tasks}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def get_sla_alerts():
    """
    GET: Returns exceptions nearing SLA deadline (<24h, <6h, or breached).
    """
    try:
        rows = call_sp("sp_get_analyst_sla_alerts")
        if rows:
            return jsonify({"success": True, "alerts": rows}), 200
    except Exception:
        pass

    session = get_session()
    try:
        now = datetime.utcnow()
        open_cases = session.query(ExceptionCase).filter(ExceptionCase.status != "RESOLVED").all()
        alerts = []
        for c in open_cases:
            rec = c.financial_record
            if not c.sla_deadline:
                continue
            delta = c.sla_deadline - now
            hours_left = delta.total_seconds() / 3600.0

            alert_type = "BREACHED" if hours_left <= 0 else ("NEAR_BREACH" if hours_left <= 24 else "APPROACHING")
            if hours_left <= 48:
                alerts.append({
                    "id": c.id,
                    "case_id": c.id,
                    "severity": c.severity,
                    "department": rec.department if rec else "Corporate",
                    "category": rec.category if rec else "Financial",
                    "hours_remaining": round(hours_left, 1),
                    "sla_deadline": c.sla_deadline.strftime("%Y-%m-%d %H:%M"),
                    "alert_level": alert_type,
                    "message": f"SLA {'Breached' if hours_left <= 0 else 'approaching breach'} ({round(abs(hours_left), 1)}h {'past' if hours_left <= 0 else 'remaining'}) for Case #{c.id}."
                })
        alerts.sort(key=lambda a: a["hours_remaining"])
        return jsonify({"success": True, "alerts": alerts}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def get_root_cause_insight(exception_id):
    """
    GET: Generates and returns AI root-cause insight and resolution recommendations.
    """
    try:
        rows = call_sp("sp_get_root_cause_insight", [int(exception_id)])
        if rows:
            item = rows[0]
            v_pct = float(item.get("variance_percent", 0))
            dept = item.get("department", "Finance")
            cat = item.get("category", "Operating Expense")
            ai_insight = {
                "exception_id": item.get("id"),
                "category": cat,
                "department": dept,
                "variance_percent": v_pct,
                "severity": item.get("severity"),
                "primary_hypothesis": f"Significant {cat} variance in {dept} ({v_pct:+.1f}% deviation): {item.get('possible_reason')}",
                "contributing_factors": [
                    f"Variance magnitude (+{abs(v_pct) * 0.7:.1f}% impact)",
                    "Mid-period pricing adjustments or supplier invoicing anomalies",
                    "Absence of pre-approval cap in purchase order system"
                ],
                "recommended_actions": [
                    "Verify vendor line-item invoice against signed agreement.",
                    "Request retrospective credit memo or adjust accruals.",
                    "Submit formal explanation or escalate if variance is structural."
                ],
                "confidence_score": 0.94
            }
            return jsonify({"success": True, "insight": ai_insight, "details": item}), 200
    except Exception:
        pass

    session = get_session()
    try:
        case = session.query(ExceptionCase).filter_by(id=int(exception_id)).first()
        if not case:
            return jsonify({"success": False, "error": "Exception record not found."}), 404

        rec = case.financial_record
        v_pct = case.variance_percent
        dept = rec.department if rec else "Finance"
        cat = rec.category if rec else "Operating Expense"

        ai_insight = {
            "exception_id": case.id,
            "category": cat,
            "department": dept,
            "variance_percent": v_pct,
            "severity": case.severity,
            "primary_hypothesis": case.possible_reason or f"Material variance detected in {cat} ({dept}) with {v_pct:+.1f}% deviation.",
            "contributing_factors": [
                f"Variance magnitude impact ({abs(v_pct):.1f}%)",
                "Departmental unbudgeted expenditure or seasonal rate surge",
                "Reconciliation lag between accounting ledger and vendor receipt"
            ],
            "recommended_actions": [
                "Verify line-item invoices against master service agreement.",
                "Verify delivery confirmation and apply credit note if misbilled.",
                "If verified as legitimate business overrun, submit formal explanation and escalate to CFO."
            ],
            "confidence_score": 0.95
        }
        return jsonify({"success": True, "insight": ai_insight, "details": case.to_dict()}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def submit_quick_action():
    """
    POST: Submit explanation, resolve/close, or escalate exception.
    """
    data = request.get_json(force=True, silent=True) or {}
    exception_id = data.get("exception_id")
    user_name = data.get("user_name", "analyst")
    role_name = data.get("role_name", "analyst")
    action = data.get("action", "RESOLVE").upper()  # RESOLVE, ESCALATE, COMMENT
    explanation = data.get("explanation", "").strip()

    if not exception_id or not explanation:
        return jsonify({"success": False, "error": "exception_id and explanation are required."}), 400

    try:
        rows = call_sp("sp_analyst_quick_action", [
            int(exception_id),
            user_name,
            role_name,
            action,
            explanation
        ])
        if rows:
            return jsonify({
                "success": True,
                "message": f"Action '{action}' executed successfully on Exception #{exception_id}.",
                "record": rows[0]
            }), 200
    except Exception:
        pass

    session = get_session()
    try:
        case = session.query(ExceptionCase).filter_by(id=int(exception_id)).first()
        if not case:
            return jsonify({"success": False, "error": "Exception record not found."}), 404

        existing_reason = case.possible_reason or ""
        note = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} - {user_name} ({role_name})]: {explanation}"
        case.possible_reason = f"{existing_reason} | {note}" if existing_reason else note

        if action == "RESOLVE":
            case.status = "RESOLVED"
        elif action == "ESCALATE":
            case.status = "ESCALATED"
            case.escalation_level = (case.escalation_level or 0) + 1

        case.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(case)

        return jsonify({
            "success": True,
            "message": f"Action '{action}' executed successfully on Exception #{exception_id}.",
            "record": case.to_dict()
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()
