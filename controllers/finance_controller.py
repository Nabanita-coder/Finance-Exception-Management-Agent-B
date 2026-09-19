from flask import request, jsonify

from services import finance_service


def health_check():
    """Simple check to confirm the API is alive. Useful for testing setup."""
    return jsonify({"status": "ok", "message": "FEMA API is running"}), 200


# =====================================================================
# FINANCIAL RECORDS
# =====================================================================
def create_financial_record():
    """
    Adds a new Budget vs Actual entry.
    Expected JSON body:
    {
        "category": "Revenue",
        "period": "2026-09",
        "department": "Sales",
        "budget_amount": 1000000,
        "actual_amount": 600000
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    required_fields = ["category", "period", "budget_amount", "actual_amount"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    try:
        record = finance_service.add_financial_record(data)
        return jsonify(record), 201
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def list_financial_records():
    """Returns every financial record stored in MySQL."""
    try:
        records = finance_service.get_all_financial_records()
        return jsonify(records), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# MONITORING (runs the detection workflow)
# =====================================================================
def run_monitoring():
    """
    Checks all financial records that don't have an exception yet,
    and creates exception cases for any unusual variance found.
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
    Returns exception cases. Supports optional filters via URL query:
    /api/exceptions?severity=CRITICAL&status=OPEN
    """
    severity = request.args.get("severity")
    status = request.args.get("status")
    try:
        exceptions = finance_service.get_exceptions(severity=severity, status=status)
        return jsonify(exceptions), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def list_overdue_exceptions():
    """Returns exception cases whose SLA deadline has already passed."""
    try:
        overdue = finance_service.get_overdue_exceptions()
        return jsonify(overdue), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def get_exception(exception_id):
    """Returns full detail of a single exception case."""
    try:
        exception = finance_service.get_exception_by_id(exception_id)
        if exception is None:
            return jsonify({"error": "Exception case not found"}), 404
        return jsonify(exception), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def update_exception(exception_id):
    """
    Updates a case -- typically its status or owner.
    Expected JSON body (any of these, all optional):
    { "status": "IN_PROGRESS", "owner_id": 2, "possible_reason": "..." }
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        updated = finance_service.update_exception(exception_id, data)
        if updated is None:
            return jsonify({"error": "Exception case not found"}), 404
        return jsonify(updated), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def escalate_exception(exception_id):
    """Escalates a case to the next, more senior owner."""
    try:
        escalated = finance_service.escalate_exception(exception_id)
        if escalated is None:
            return jsonify({"error": "Exception case not found"}), 404
        return jsonify(escalated), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# DASHBOARD
# =====================================================================
def dashboard():
    """Returns summary numbers for the dashboard UI."""
    try:
        summary = finance_service.get_dashboard_summary()
        return jsonify(summary), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# RAG FINANCE CHATBOT
# =====================================================================
def chat():
    """
    Expected JSON body: { "question": "Why did revenue decrease?" }
    Answers using only real FEMA data (RAG: ChromaDB + LLM).
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


def execute_stored_procedure():
    """
    Directly calls any registered MySQL Stored Procedure and returns its answer.
    Expected JSON body:
    {
        "sp_name": "sp_get_dashboard_summary",
        "params": []
    }
    or:
    {
        "sp_name": "sp_add_financial_record",
        "params": ["Revenue", "2026-09", "Sales", 1000000, 600000]
    }
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
        from dbConnection.db import call_sp
        results = call_sp(sp_name, params)
        return jsonify({
            "status": "success",
            "sp_name": sp_name,
            "data": results
        }), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


# =====================================================================
# OWNERS
# =====================================================================
def list_owners():
    """Returns all owners with their real-time active case counts."""
    try:
        owners = finance_service.get_all_owners()
        return jsonify(owners), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


def create_owner():
    """Adds a new team member / owner dynamically."""
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name") or not data.get("role"):
        return jsonify({"error": "name and role are required"}), 400
    try:
        owner = finance_service.add_owner(data)
        return jsonify(owner), 201
    except Exception as error:
        return jsonify({"error": str(error)}), 500


