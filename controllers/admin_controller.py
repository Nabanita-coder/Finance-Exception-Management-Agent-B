"""
controllers/admin_controller.py
--------------------------------
HTTP Controller for System Administrator (Role 0):
- System Health & Uptime (ERP, EPM, Banking API)
- AI Models & Thresholds Status / Calibration
- User & Access Management
- System Error Logs & Notification History
All data managed via Stored Procedures.
"""

from flask import request, jsonify
from dbConnection.db import call_sp


def get_system_health():
    """
    GET: Returns real-time connectivity and uptime status of ERP, EPM, and Banking APIs
    Managed via SP: sp_get_system_health
    """
    try:
        rows = call_sp("sp_get_system_health")
        return jsonify({"success": True, "integrations": rows}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_ai_thresholds():
    """
    GET: Returns active anomaly detection parameters & rule engine thresholds
    Managed via SP: sp_get_ai_thresholds
    """
    try:
        rows = call_sp("sp_get_ai_thresholds")
        return jsonify({"success": True, "thresholds": rows}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def update_ai_threshold():
    """
    POST / PUT: Updates a specific AI threshold parameter
    Managed via SP: sp_update_ai_threshold
    """
    data = request.get_json(force=True, silent=True) or {}
    param_key = data.get("param_key")
    param_value = str(data.get("param_value", ""))
    updated_by = data.get("updated_by", "admin")

    if not param_key or not param_value:
        return jsonify({"success": False, "error": "param_key and param_value are required."}), 400

    try:
        rows = call_sp("sp_update_ai_threshold", [param_key, param_value, updated_by])
        updated = rows[0] if rows else {}
        return jsonify({
            "success": True,
            "message": f"Threshold '{param_key}' updated to '{param_value}'.",
            "threshold": updated
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def list_users():
    """
    GET: Returns user directory, assigned roles, and active statuses
    Managed via SP: sp_get_users_management
    """
    try:
        rows = call_sp("sp_get_users_management")
        return jsonify({"success": True, "users": rows}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def update_user_role():
    """
    POST: Modifies an existing user's role
    Managed via SP: sp_update_user_role
    """
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    role_id = data.get("role_id")
    admin_name = data.get("admin_name", "admin")

    if user_id is None or role_id is None:
        return jsonify({"success": False, "error": "user_id and role_id are required."}), 400

    try:
        rows = call_sp("sp_update_user_role", [int(user_id), int(role_id), admin_name])
        return jsonify({
            "success": True,
            "message": f"User ID #{user_id} role updated successfully.",
            "user": rows[0] if rows else None
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def get_system_logs():
    """
    GET: Returns system sync logs, data ingestion alerts, and error history
    Managed via SP: sp_get_system_logs
    """
    try:
        rows = call_sp("sp_get_system_logs")
        return jsonify({"success": True, "logs": rows}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
