"""
controllers/finance_controller.py
-----------------------------------
This file is the "receptionist" of FEMA. It defines every API endpoint
(URL) that the outside world (our UI, Postman, or another program) can
call. Each function here:
  1. Reads what the caller sent (JSON body or URL parameters)
  2. Calls the correct function in services/finance_service.py to do
     the real work
  3. Sends back a JSON response

No business logic (math, decisions) happens in this file -- it only
passes messages back and forth.
"""

from flask import Blueprint, request, jsonify

from services import finance_service

# A Blueprint is Flask's way of grouping related routes together.
# app.py will register this blueprint under the "/api" prefix.
finance_bp = Blueprint("finance_bp", __name__)


@finance_bp.route("/health", methods=["GET"])
def health_check():
    """Simple check to confirm the API is alive. Useful for testing setup."""
    return jsonify({"status": "ok", "message": "FEMA API is running"}), 200


# =====================================================================
# FINANCIAL RECORDS
# =====================================================================
@finance_bp.route("/financial-records", methods=["POST"])
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


@finance_bp.route("/financial-records", methods=["GET"])
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
@finance_bp.route("/monitor", methods=["POST"])
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
@finance_bp.route("/exceptions", methods=["GET"])
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


@finance_bp.route("/exceptions/overdue", methods=["GET"])
def list_overdue_exceptions():
    """Returns exception cases whose SLA deadline has already passed."""
    try:
        overdue = finance_service.get_overdue_exceptions()
        return jsonify(overdue), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@finance_bp.route("/exceptions/<int:exception_id>", methods=["GET"])
def get_exception(exception_id):
    """Returns full detail of a single exception case."""
    try:
        exception = finance_service.get_exception_by_id(exception_id)
        if exception is None:
            return jsonify({"error": "Exception case not found"}), 404
        return jsonify(exception), 200
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@finance_bp.route("/exceptions/<int:exception_id>", methods=["PUT"])
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


@finance_bp.route("/exceptions/<int:exception_id>/escalate", methods=["POST"])
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
@finance_bp.route("/dashboard", methods=["GET"])
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
@finance_bp.route("/chat", methods=["POST"])
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
