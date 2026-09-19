from flask import request, jsonify
from dbConnection.db import call_sp
from services import finance_service


def health_check():
    """Simple check to confirm the API is alive."""
    return jsonify({"status": "ok", "message": "FEMA API is running"}), 200


# =====================================================================
# FINANCIAL RECORDS
# =====================================================================
def create_financial_record():
    """
    POST: Adds a new Budget vs Actual entry via Stored Procedure 'sp_add_financial_record'.
    """
    data = request.get_json(force=True, silent=True) or {}
    required_fields = ["category", "period", "budget_amount", "actual_amount"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        category = data["category"]
        period = data["period"]
        department = data.get("department")
        budget_amount = float(data["budget_amount"])
        actual_amount = float(data["actual_amount"])

        rows = call_sp(
            "sp_add_financial_record",
            [category, period, department, budget_amount, actual_amount],
        )
        record = rows[0] if rows else {}
        return jsonify(record), 201
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def list_financial_records():
    """
    GET: Returns all financial records via Stored Procedure 'sp_get_all_financial_records'.
    """
    try:
        rows = call_sp("sp_get_all_financial_records")
        return jsonify(rows), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# MONITORING (AI Detection Workflow)
# =====================================================================
def run_monitoring():
    """
    POST: Runs the exception detection workflow.
    """
    try:
        result = finance_service.run_monitoring()
        return jsonify(result), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# EXCEPTION CASES
# =====================================================================
def list_exceptions():
    """
    GET: Returns exception cases via Stored Procedure 'sp_get_exceptions'.
    Supports query parameters: ?severity=CRITICAL&status=OPEN
    """
    severity = request.args.get("severity")
    status = request.args.get("status")
    try:
        rows = call_sp("sp_get_exceptions", [severity, status])
        # Format owner and financial_record nested objects for frontend compatibility
        formatted = []
        for r in rows:
            formatted.append({
                "id": r.get("id"),
                "financial_record_id": r.get("financial_record_id"),
                "variance_percent": r.get("variance_percent"),
                "severity": r.get("severity"),
                "possible_reason": r.get("possible_reason"),
                "status": r.get("status"),
                "owner_id": r.get("owner_id"),
                "sla_deadline": str(r.get("sla_deadline")) if r.get("sla_deadline") else None,
                "escalation_level": r.get("escalation_level"),
                "created_at": str(r.get("created_at")) if r.get("created_at") else None,
                "updated_at": str(r.get("updated_at")) if r.get("updated_at") else None,
                "financial_record": {
                    "id": r.get("financial_record_id"),
                    "category": r.get("record_category"),
                    "period": r.get("record_period"),
                    "department": r.get("record_department"),
                    "budget_amount": r.get("record_budget"),
                    "actual_amount": r.get("record_actual"),
                } if r.get("financial_record_id") else None,
                "owner": {
                    "id": r.get("owner_id"),
                    "name": r.get("owner_name"),
                    "email": r.get("owner_email"),
                    "role": r.get("owner_role"),
                    "level": r.get("owner_level"),
                } if r.get("owner_id") else None,
            })
        return jsonify(formatted), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def list_overdue_exceptions():
    """
    GET: Returns overdue exception cases via Stored Procedure 'sp_get_overdue_exceptions'.
    """
    try:
        rows = call_sp("sp_get_overdue_exceptions")
        formatted = []
        for r in rows:
            formatted.append({
                "id": r.get("id"),
                "financial_record_id": r.get("financial_record_id"),
                "variance_percent": r.get("variance_percent"),
                "severity": r.get("severity"),
                "possible_reason": r.get("possible_reason"),
                "status": r.get("status"),
                "owner_id": r.get("owner_id"),
                "sla_deadline": str(r.get("sla_deadline")) if r.get("sla_deadline") else None,
                "escalation_level": r.get("escalation_level"),
                "created_at": str(r.get("created_at")) if r.get("created_at") else None,
                "updated_at": str(r.get("updated_at")) if r.get("updated_at") else None,
                "financial_record": {
                    "id": r.get("financial_record_id"),
                    "category": r.get("record_category"),
                    "period": r.get("record_period"),
                    "department": r.get("record_department"),
                    "budget_amount": r.get("record_budget"),
                    "actual_amount": r.get("record_actual"),
                } if r.get("financial_record_id") else None,
                "owner": {
                    "id": r.get("owner_id"),
                    "name": r.get("owner_name"),
                    "email": r.get("owner_email"),
                    "role": r.get("owner_role"),
                    "level": r.get("owner_level"),
                } if r.get("owner_id") else None,
            })
        return jsonify(formatted), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def get_exception(exception_id):
    """
    GET: Returns details of a single exception via Stored Procedure 'sp_get_exception_by_id'.
    """
    try:
        rows = call_sp("sp_get_exception_by_id", [exception_id])
        if not rows:
            return jsonify({"error": "Exception case not found"}), 404
        r = rows[0]
        case_data = {
            "id": r.get("id"),
            "financial_record_id": r.get("financial_record_id"),
            "variance_percent": r.get("variance_percent"),
            "severity": r.get("severity"),
            "possible_reason": r.get("possible_reason"),
            "status": r.get("status"),
            "owner_id": r.get("owner_id"),
            "sla_deadline": str(r.get("sla_deadline")) if r.get("sla_deadline") else None,
            "escalation_level": r.get("escalation_level"),
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            "updated_at": str(r.get("updated_at")) if r.get("updated_at") else None,
            "financial_record": {
                "id": r.get("financial_record_id"),
                "category": r.get("record_category"),
                "period": r.get("record_period"),
                "department": r.get("record_department"),
                "budget_amount": r.get("record_budget"),
                "actual_amount": r.get("record_actual"),
            } if r.get("financial_record_id") else None,
            "owner": {
                "id": r.get("owner_id"),
                "name": r.get("owner_name"),
                "email": r.get("owner_email"),
                "role": r.get("owner_role"),
                "level": r.get("owner_level"),
            } if r.get("owner_id") else None,
        }
        return jsonify(case_data), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def update_exception(exception_id):
    """
    PUT: Updates status, owner, or reason via Stored Procedure 'sp_update_exception'.
    """
    data = request.get_json(force=True, silent=True) or {}
    status = data.get("status")
    owner_id = data.get("owner_id")
    possible_reason = data.get("possible_reason")

    try:
        rows = call_sp(
            "sp_update_exception",
            [exception_id, status, owner_id, possible_reason],
        )
        if not rows:
            return jsonify({"error": "Exception case not found"}), 404
        r = rows[0]
        updated = {
            "id": r.get("id"),
            "financial_record_id": r.get("financial_record_id"),
            "variance_percent": r.get("variance_percent"),
            "severity": r.get("severity"),
            "possible_reason": r.get("possible_reason"),
            "status": r.get("status"),
            "owner_id": r.get("owner_id"),
            "sla_deadline": str(r.get("sla_deadline")) if r.get("sla_deadline") else None,
            "escalation_level": r.get("escalation_level"),
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            "updated_at": str(r.get("updated_at")) if r.get("updated_at") else None,
        }
        return jsonify(updated), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def escalate_exception(exception_id):
    """
    POST: Escalates a case via Stored Procedure 'sp_escalate_exception'.
    """
    try:
        rows = call_sp("sp_escalate_exception", [exception_id])
        if not rows:
            return jsonify({"error": "Exception case not found"}), 404
        r = rows[0]
        escalated = {
            "id": r.get("id"),
            "financial_record_id": r.get("financial_record_id"),
            "variance_percent": r.get("variance_percent"),
            "severity": r.get("severity"),
            "possible_reason": r.get("possible_reason"),
            "status": r.get("status"),
            "owner_id": r.get("owner_id"),
            "sla_deadline": str(r.get("sla_deadline")) if r.get("sla_deadline") else None,
            "escalation_level": r.get("escalation_level"),
            "created_at": str(r.get("created_at")) if r.get("created_at") else None,
            "updated_at": str(r.get("updated_at")) if r.get("updated_at") else None,
        }
        return jsonify(escalated), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# DASHBOARD
# =====================================================================
def dashboard():
    """
    GET: Returns dashboard summary via Stored Procedure 'sp_get_dashboard_summary'.
    """
    try:
        rows = call_sp("sp_get_dashboard_summary")
        if not rows:
            return jsonify({}), 200
        r = rows[0]
        summary = {
            "total_financial_records": r.get("total_financial_records", 0),
            "total_exceptions": r.get("total_exceptions", 0),
            "exceptions_by_severity": {
                "LOW": r.get("count_low", 0),
                "MEDIUM": r.get("count_medium", 0),
                "HIGH": r.get("count_high", 0),
                "CRITICAL": r.get("count_critical", 0),
            },
            "exceptions_by_status": {
                "OPEN": r.get("count_open", 0),
                "IN_PROGRESS": r.get("count_in_progress", 0),
                "RESOLVED": r.get("count_resolved", 0),
                "ESCALATED": r.get("count_escalated", 0),
            },
            "overdue_exceptions": r.get("overdue_exceptions", 0),
        }
        return jsonify(summary), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# RAG FINANCE CHATBOT
# =====================================================================
def chat():
    """
    POST: Expected JSON body: { "question": "Why did revenue decrease?" }
    """
    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Please provide a 'question' field."}), 400

    try:
        result = finance_service.chat_with_rag(question)
        return jsonify(result), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# DIRECT STORED PROCEDURE EXECUTION
# =====================================================================
def execute_stored_procedure():
    """
    POST: Directly calls any registered MySQL Stored Procedure and returns result.
    """
    data = request.get_json(force=True, silent=True) or {}
    sp_name = data.get("sp_name")
    params = data.get("params", [])

    if not sp_name:
        return jsonify({"error": "Missing 'sp_name' in request body"}), 400

    allowed_sps = {
        "sp_add_financial_record",
        "sp_get_all_financial_records",
        "sp_get_unprocessed_financial_records",
        "sp_create_exception_case",
        "sp_get_exceptions",
        "sp_get_exception_by_id",
        "sp_get_overdue_exceptions",
        "sp_update_exception",
        "sp_escalate_exception",
        "sp_get_dashboard_summary",
    }

    if sp_name not in allowed_sps:
        return jsonify({"error": f"Procedure '{sp_name}' is not in allowed list"}), 403

    try:
        results = call_sp(sp_name, params)
        return jsonify({
            "status": "success",
            "sp_name": sp_name,
            "data": results,
        }), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500

