"""
services/auth_service.py
------------------------
Authentication and authorization service for FEMA backend.
Handles:
- Initializing and seeding roles (0: admin, 1: user) and default users
- Password hashing & verification
- JWT Token issuance and validation
- Role-based decorators (@token_required, @admin_required)
"""

import os
from datetime import datetime, timedelta
from functools import wraps
import jwt
from flask import request, jsonify

from dbConnection.db import engine, get_session
from models.finance_models import Base, Role, User

JWT_SECRET = os.getenv("JWT_SECRET", "fema-super-secret-jwt-key-2026-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 24))


# =====================================================================
# DATABASE INITIALIZATION & SEEDING
# =====================================================================
def init_auth_db():
    """
    Ensures 'roles' and 'users' tables exist and seeds default accounts:
    Roles:
      - ID 0: admin
      - ID 1: user
    Users:
      - admin / admin123 (role_id: 0)
      - user / user123 (role_id: 1)
    """
    try:
        # Create tables if not present
        Base.metadata.create_all(bind=engine, tables=[Role.__table__, User.__table__])

        session = get_session()
        try:
            # 1. Seed Roles
            roles_to_seed = [
                (0, "admin", "Administrator with full system privileges and escalation authority"),
                (1, "user", "Standard user with view and record management access"),
            ]
            for role_id, role_name, role_desc in roles_to_seed:
                existing_role = session.query(Role).filter_by(id=role_id).first()
                if not existing_role:
                    new_role = Role(id=role_id, name=role_name, description=role_desc)
                    session.add(new_role)
            session.commit()

            # 2. Seed Default Admin and Standard User
            default_users = [
                {
                    "username": "admin",
                    "email": "admin@fema.local",
                    "password": "admin123",
                    "full_name": "System Administrator",
                    "role_id": 0,
                },
                {
                    "username": "user",
                    "email": "user@fema.local",
                    "password": "user123",
                    "full_name": "Finance User",
                    "role_id": 1,
                },
            ]

            for u_data in default_users:
                existing_user = (
                    session.query(User)
                    .filter((User.username == u_data["username"]) | (User.email == u_data["email"]))
                    .first()
                )
                if not existing_user:
                    user_obj = User(
                        username=u_data["username"],
                        email=u_data["email"],
                        role_id=u_data["role_id"],
                        full_name=u_data["full_name"],
                        is_active=1,
                    )
                    user_obj.set_password(u_data["password"])
                    session.add(user_obj)
            session.commit()
            print("[AuthService] Roles and default user accounts initialized successfully.")
        except Exception as e:
            session.rollback()
            print(f"[AuthService] Database initialization error: {e}")
        finally:
            session.close()
    except Exception as outer_e:
        print(f"[AuthService] Table creation warning: {outer_e}")


# =====================================================================
# AUTHENTICATION LOGIC
# =====================================================================
def generate_token(user: User) -> str:
    """Generates a signed JWT token containing user details and role info."""
    role_name = user.role.name if user.role else ("admin" if user.role_id == 0 else "user")
    now = datetime.utcnow()
    payload = {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role_id": user.role_id,
        "role": role_name,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid authentication token.")


def authenticate(identifier: str, password: str):
    """
    Authenticates by username or email and password.
    Returns (result_dict, error_message).
    """
    if not identifier or not password:
        return None, "Username/email and password are required."

    session = get_session()
    try:
        ident = identifier.strip().lower()
        user = (
            session.query(User)
            .filter((User.username.ilike(ident)) | (User.email.ilike(ident)))
            .first()
        )

        if not user or not user.check_password(password):
            return None, "Invalid credentials. Please check your username/email and password."

        if not user.is_active:
            return None, "This user account has been deactivated. Please contact an admin."

        token = generate_token(user)
        user_dict = user.to_dict()

        return {
            "token": token,
            "user": user_dict,
        }, None
    finally:
        session.close()


def register_user(data: dict):
    """
    Registers a new user.
    Required keys: username, email, password
    Optional: full_name, role_id (default 1 = user)
    """
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or username).strip()
    role_id = data.get("role_id", 1)

    if not username or not email or not password:
        return None, "Username, email, and password are required."

    if role_id not in (0, 1):
        return None, "Invalid role_id. Must be 0 (admin) or 1 (user)."

    session = get_session()
    try:
        # Check if username or email already exists
        existing = (
            session.query(User)
            .filter((User.username.ilike(username)) | (User.email.ilike(email)))
            .first()
        )
        if existing:
            if existing.username.lower() == username.lower():
                return None, f"Username '{username}' is already taken."
            return None, f"Email '{email}' is already registered."

        new_user = User(
            username=username,
            email=email,
            full_name=full_name,
            role_id=role_id,
            is_active=1,
        )
        new_user.set_password(password)
        session.add(new_user)
        session.commit()

        token = generate_token(new_user)
        return {
            "token": token,
            "user": new_user.to_dict(),
        }, None
    except Exception as e:
        session.rollback()
        return None, str(e)
    finally:
        session.close()


def get_user_by_id(user_id: int):
    """Fetches user profile by user_id."""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        return user.to_dict() if user else None
    finally:
        session.close()


def get_all_roles():
    """Returns list of available system roles."""
    session = get_session()
    try:
        roles = session.query(Role).order_by(Role.id.asc()).all()
        return [r.to_dict() for r in roles]
    finally:
        session.close()


# =====================================================================
# ROUTE DECORATORS FOR PROTECTION
# =====================================================================
def get_bearer_token() -> str:
    """Extracts Bearer token from the incoming request Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return ""


def token_required(f):
    """Decorator requiring a valid JWT token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            return jsonify({"error": "Authorization token is missing. Please provide a Bearer token."}), 401
        try:
            current_user = decode_token(token)
        except ValueError as e:
            return jsonify({"error": str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator requiring that the authenticated user has role_id == 0 (admin)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            return jsonify({"error": "Authorization token is missing."}), 401
        try:
            current_user = decode_token(token)
        except ValueError as e:
            return jsonify({"error": str(e)}), 401

        if current_user.get("role_id") != 0:
            return jsonify({"error": "Access denied: Admin privileges required."}), 403

        return f(current_user, *args, **kwargs)
    return decorated
