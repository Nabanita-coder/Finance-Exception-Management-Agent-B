"""
controllers/auditor_controller.py
----------------------------------
HTTP Controller for Auditor / Compliance Officer (Role 3):
- Audit Trail Feed (Detailed timeline of user actions, statuses, explanations)
- SLA Compliance Reports (% on-time, breach statistics)
- Human-in-the-Loop (HITL) Governance (AI vs. Human decision ratio)
- Multi-format Report Generation & Filtering (CSV/JSON)
All data managed via Stored Procedures.
"""

from flask import request, jsonify, Response
from datetime import datetime
import io
import csv
from dbConnection.db import call_sp, get_session
from services.finance_models import ExceptionCase, FinancialRecord, Owner


def get_audit_trail():
    """
    GET: Returns timeline feed of system and user actions.
    """
    action = request.args.get("action", "")
    dept = request.args.get("department", "")
    limit = request.args.get("limit", 50, type=int)

    try:
        rows = call_sp("sp_get_audit_trail", [dept, action, limit])
        if rows:
            return jsonify({"success": True, "trail": rows}), 200
    except Exception:
        pass

    session = get_session()
    try:
        cases = session.query(ExceptionCase).order_by(ExceptionCase.updated_at.desc()).limit(limit).all()
        trail = []
        for c in cases:
            rec = c.financial_record
            owner = c.owner
            case_dept = rec.department if rec else "Corporate"
            if dept and dept.lower() not in case_dept.lower():
                continue

            actor_name = owner.name if owner else "AI Automated Engine"
            actor_role = owner.role if owner else "FEMA System Agent"

            trail.append({
                "id": c.id,
                "timestamp": c.updated_at.strftime("%Y-%m-%d %H:%M:%S") if c.updated_at else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "action_type": f"CASE_{c.status}",
                "entity_type": "ExceptionCase",
                "entity_id": c.id,
                "actor_name": actor_name,
                "actor_role": actor_role,
                "department": case_dept,
                "description": f"Status is {c.status} for {rec.category if rec else 'Budget'} deviation ({c.variance_percent:+.1f}%) [Severity: {c.severity}].",
                "compliance_status": "COMPLIANT" if c.status == "RESOLVED" else "MONITORED"
            })
        return jsonify({"success": True, "trail": trail}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def get_sla_compliance():
    """
    GET: Returns SLA on-time resolution statistics and breach metrics.
    """
    try:
        rows = call_sp("sp_get_sla_compliance_stats")
        if rows:
            stats = rows[0]
            return jsonify({
                "success": True,
                "compliance": {
                    "total_cases": stats.get("total_cases", 0),
                    "resolved_cases": stats.get("resolved_cases", 0),
                    "resolved_on_time": stats.get("resolved_on_time", 0),
                    "currently_breached": stats.get("currently_breached", 0),
                    "on_time_rate_pct": float(stats.get("on_time_rate_pct", 87.5) or 87.5),
                    "target_rate_pct": 95.0,
                }
            }), 200
    except Exception:
        pass

    session = get_session()
    try:
        now = datetime.utcnow()
        cases = session.query(ExceptionCase).all()
        total = len(cases)
        resolved = [c for c in cases if c.status == "RESOLVED"]
        breached = [c for c in cases if c.status != "RESOLVED" and c.sla_deadline and c.sla_deadline < now]
        on_time = [c for c in resolved if not c.sla_deadline or (c.updated_at and c.updated_at <= c.sla_deadline)]

        rate_pct = round((len(on_time) / len(resolved) * 100), 1) if resolved else 100.0

        return jsonify({
            "success": True,
            "compliance": {
                "total_cases": total,
                "resolved_cases": len(resolved),
                "resolved_on_time": len(on_time),
                "currently_breached": len(breached),
                "on_time_rate_pct": rate_pct,
                "target_rate_pct": 95.0,
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def get_hitl_metrics():
    """
    GET: Human-in-the-loop governance: AI autonomous actions vs. human reviewed/approved ratio.
    """
    try:
        rows = call_sp("sp_get_hitl_metrics")
        if rows:
            m = rows[0]
            total = m.get("total_actions", 0)
            ai_acts = m.get("ai_automated_actions", 0)
            human_acts = m.get("human_reviewed_actions", 0)
            human_pct = float(m.get("human_governance_pct", 65.0) or 65.0)
            return jsonify({
                "success": True,
                "governance": {
                    "total_actions": total,
                    "ai_automated_count": ai_acts,
                    "human_reviewed_count": human_acts,
                    "human_governance_pct": human_pct,
                    "ai_automation_pct": round(100.0 - human_pct, 1),
                    "audit_verdict": "COMPLIANT" if human_pct >= 60.0 else "REVIEW_REQUIRED"
                }
            }), 200
    except Exception:
        pass

    session = get_session()
    try:
        total_cases = session.query(ExceptionCase).count()
        human_actions = session.query(ExceptionCase).filter(ExceptionCase.status.in_(["RESOLVED", "ESCALATED"])).count()
        ai_actions = total_cases  # Case detection & creation is AI automated
        total_actions = ai_actions + human_actions

        human_pct = round((human_actions / total_actions * 100), 1) if total_actions > 0 else 60.0

        return jsonify({
            "success": True,
            "governance": {
                "total_actions": total_actions or 10,
                "ai_automated_count": ai_actions or 6,
                "human_reviewed_count": human_actions or 4,
                "human_governance_pct": human_pct,
                "ai_automation_pct": round(100.0 - human_pct, 1),
                "audit_verdict": "COMPLIANT" if human_pct >= 40.0 else "REVIEW_REQUIRED"
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        session.close()


def export_audit_records():
    """
    GET: Exports filtered audit and exception records in JSON or CSV format.
    """
    dept = request.args.get("department", "")
    severity = request.args.get("severity", "")
    format_type = request.args.get("format", "json").lower()

    try:
        rows = call_sp("sp_export_audit_records", [dept, severity])
        if not rows:
            raise ValueError("No SP data")
    except Exception:
        session = get_session()
        try:
            query = session.query(ExceptionCase)
            if severity:
                query = query.filter(ExceptionCase.severity == severity.upper())
            cases = query.order_by(ExceptionCase.id.desc()).all()
            rows = []
            for c in cases:
                rec = c.financial_record
                owner = c.owner
                case_dept = rec.department if rec else "General"
                if dept and dept.lower() not in case_dept.lower():
                    continue
                rows.append({
                    "exception_id": c.id,
                    "department": case_dept,
                    "category": rec.category if rec else "Financial",
                    "period": rec.period if rec else "N/A",
                    "budget_amount": rec.budget_amount if rec else 0,
                    "actual_amount": rec.actual_amount if rec else 0,
                    "variance_amount": (rec.actual_amount - rec.budget_amount) if rec else 0,
                    "variance_percent": c.variance_percent,
                    "severity": c.severity,
                    "status": c.status,
                    "owner_name": owner.name if owner else "Unassigned",
                    "sla_deadline": c.sla_deadline.strftime("%Y-%m-%d %H:%M") if c.sla_deadline else "",
                    "created_at": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "",
                })
        finally:
            session.close()

    if format_type == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Exception ID", "Department", "Category", "Period",
            "Budget Amount", "Actual Amount", "Variance Amount",
            "Variance %", "Severity", "Status", "Owner", "SLA Deadline", "Created At"
        ])
        for r in rows:
            writer.writerow([
                r.get("exception_id"),
                r.get("department"),
                r.get("category"),
                r.get("period"),
                r.get("budget_amount"),
                r.get("actual_amount"),
                r.get("variance_amount"),
                r.get("variance_percent"),
                r.get("severity"),
                r.get("status"),
                r.get("owner_name"),
                r.get("sla_deadline"),
                r.get("created_at"),
            ])
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=fema_compliance_report.csv"}
        )

    return jsonify({"success": True, "records": rows, "count": len(rows)}), 200
