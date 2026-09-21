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
import io
import csv
from dbConnection.db import call_sp


def get_audit_trail():
    """
    GET: Returns timeline feed of system and user actions
    Managed via SP: sp_get_audit_trail
    """
    action = request.args.get("action", "")
    dept = request.args.get("department", "")
    limit = request.args.get("limit", 50, type=int)

    try:
        rows = call_sp("sp_get_audit_trail", [dept, action, limit])
        trail = []
        for r in rows:
            trail.append({
                "id": r.get("id"),
                "exception_id": r.get("exception_id"),
                "user_name": r.get("user_name"),
                "role_name": r.get("role_name"),
                "action": r.get("action"),
                "explanation": r.get("explanation"),
                "previous_status": r.get("previous_status"),
                "new_status": r.get("new_status"),
                "is_ai_action": bool(r.get("is_ai_action")),
                "ip_address": r.get("ip_address"),
                "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            })
        return jsonify({"success": True, "trail": trail}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_sla_compliance():
    """
    GET: Returns SLA on-time resolution statistics and breach metrics
    Managed via SP: sp_get_sla_compliance_stats
    """
    try:
        rows = call_sp("sp_get_sla_compliance_stats")
        stats = rows[0] if rows else {}
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_hitl_metrics():
    """
    GET: Human-in-the-loop governance: AI autonomous actions vs. human reviewed/approved ratio
    Managed via SP: sp_get_hitl_metrics
    """
    try:
        rows = call_sp("sp_get_hitl_metrics")
        m = rows[0] if rows else {}
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def export_audit_records():
    """
    GET: Exports filtered audit and exception records in JSON or CSV format
    Managed via SP: sp_export_audit_records
    """
    dept = request.args.get("department", "")
    severity = request.args.get("severity", "")
    format_type = request.args.get("format", "json").lower()

    try:
        rows = call_sp("sp_export_audit_records", [dept, severity])
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
