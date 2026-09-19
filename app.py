import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from controllers import finance_controller, auth_controller
from services import auth_service

# Load .env variables (DB_HOST, DB_PASSWORD, ANTHROPIC_API_KEY, etc.)
load_dotenv()

app = Flask(__name__)
CORS(app)

# Ensure roles and users tables & initial seed accounts are initialized
with app.app_context():
    try:
        auth_service.init_auth_db()
    except Exception as _e:
        print(f"Warning: Could not initialize auth DB on startup: {_e}")


# =====================================================================
# ROOT & HEALTH CHECK
# =====================================================================
@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health_check():
    return finance_controller.health_check()


# =====================================================================
# FINANCIAL RECORDS
# =====================================================================
@app.route("/financial-records", methods=["POST"])
@app.route("/api/financial-records", methods=["POST"])
def create_financial_record():
    return finance_controller.create_financial_record()


@app.route("/financial-records", methods=["GET"])
@app.route("/api/financial-records", methods=["GET"])
def list_financial_records():
    return finance_controller.list_financial_records()


# =====================================================================
# MONITORING
# =====================================================================
@app.route("/monitor", methods=["POST"])
@app.route("/api/monitor", methods=["POST"])
def run_monitoring():
    return finance_controller.run_monitoring()


# =====================================================================
# EXCEPTION CASES
# =====================================================================
@app.route("/exceptions", methods=["GET"])
@app.route("/api/exceptions", methods=["GET"])
def list_exceptions():
    return finance_controller.list_exceptions()


@app.route("/exceptions/overdue", methods=["GET"])
@app.route("/api/exceptions/overdue", methods=["GET"])
def list_overdue_exceptions():
    return finance_controller.list_overdue_exceptions()


@app.route("/exceptions/<int:exception_id>", methods=["GET"])
@app.route("/api/exceptions/<int:exception_id>", methods=["GET"])
def get_exception(exception_id):
    return finance_controller.get_exception(exception_id)


@app.route("/exceptions/<int:exception_id>", methods=["PUT"])
@app.route("/api/exceptions/<int:exception_id>", methods=["PUT"])
def update_exception(exception_id):
    return finance_controller.update_exception(exception_id)


@app.route("/exceptions/<int:exception_id>/escalate", methods=["POST"])
@app.route("/api/exceptions/<int:exception_id>/escalate", methods=["POST"])
def escalate_exception(exception_id):
    return finance_controller.escalate_exception(exception_id)


# =====================================================================
# DASHBOARD
# =====================================================================
@app.route("/dashboard", methods=["GET"])
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    return finance_controller.dashboard()


# =====================================================================
# RAG FINANCE CHATBOT
# =====================================================================
@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    return finance_controller.chat()


# =====================================================================
# DYNAMIC OWNERS
# =====================================================================
@app.route("/owners", methods=["GET"])
@app.route("/api/owners", methods=["GET"])
def list_owners():
    return finance_controller.list_owners()


@app.route("/owners", methods=["POST"])
@app.route("/api/owners", methods=["POST"])
def create_owner():
    return finance_controller.create_owner()


# =====================================================================
# AUTHENTICATION (ADMIN & USER)
# =====================================================================
@app.route("/auth/login", methods=["POST"])
@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    return auth_controller.login()


@app.route("/auth/register", methods=["POST"])
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    return auth_controller.register()


@app.route("/auth/me", methods=["GET"])
@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    return auth_controller.me()


@app.route("/auth/roles", methods=["GET"])
@app.route("/api/auth/roles", methods=["GET"])
def auth_roles():
    return auth_controller.list_roles()



if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    print(f"Starting FEMA on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)


