"""
controllers/auth_controller.py
------------------------------
HTTP Controller handling authentication requests:
- POST /api/auth/login
- POST /api/auth/register
- GET  /api/auth/me
- GET  /api/auth/roles
"""

from flask import request, jsonify
from services import auth_service


def login():
    """
    Handles login for both Admin (role_id: 0) and User (role_id: 1).
    Accepts JSON body:
    {
        "username": "admin",  # or "email"
        "password": "admin123"
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    identifier = data.get("username") or data.get("email") or data.get("identifier")
    password = data.get("password")

    if not identifier or not password:
        return jsonify({
            "success": False,
            "error": "Both username/email and password are required."
        }), 400

    result, err = auth_service.authenticate(identifier, password)
    if err:
        status_code = 403 if "deactivated" in err.lower() else 401
        return jsonify({
            "success": False,
            "error": err
        }), status_code

    return jsonify({
        "success": True,
        "message": f"Welcome back, {result['user']['full_name'] or result['user']['username']}!",
        "token": result["token"],
        "user": result["user"]
    }), 200


def register():
    """
    Registers a new account.
    Accepts JSON body:
    {
        "username": "johndoe",
        "email": "johndoe@company.com",
        "password": "securepassword",
        "full_name": "John Doe",
        "role_id": 1  # 0 for admin, 1 for user (defaults to 1)
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    result, err = auth_service.register_user(data)

    if err:
        return jsonify({
            "success": False,
            "error": err
        }), 400

    return jsonify({
        "success": True,
        "message": "User registered successfully.",
        "token": result["token"],
        "user": result["user"]
    }), 201


@auth_service.token_required
def me(current_user):
    """
    Returns current authenticated user details extracted from Bearer JWT token.
    Header: Authorization: Bearer <token>
    """
    user = auth_service.get_user_by_id(current_user["user_id"])
    if not user:
        return jsonify({
            "success": False,
            "error": "User record not found."
        }), 404

    return jsonify({
        "success": True,
        "user": user
    }), 200


def list_roles():
    """Returns available roles in the system."""
    roles = auth_service.get_all_roles()
    return jsonify({
        "success": True,
        "roles": roles
    }), 200
