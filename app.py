import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from controllers import (
    finance_controller,
    auth_controller,
    admin_controller,
    analyst_controller,
    cfo_controller,
    auditor_controller,
)
from services import auth_service, finance_service

# Load .env variables (DB_HOST, DB_PASSWORD, ANTHROPIC_API_KEY, etc.)
load_dotenv()

app = Flask(__name__)
CORS(app)

# Ensure roles, users, and dynamic AI thresholds tables & seed data are initialized
with app.app_context():
    try:
        auth_service.init_auth_db()
        finance_service.init_thresholds_db()
    except Exception as _e:
        print(f"Warning: Could not initialize DB on startup: {_e}")


# =====================================================================
# ROOT & HEALTH CHECK
# =====================================================================
@app.route("/", methods=["GET"])
def home():
    return finance_controller.health_check()


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
# DIRECT STORED PROCEDURE EXECUTION
# =====================================================================
@app.route("/sp", methods=["POST"])
@app.route("/api/sp", methods=["POST"])
def execute_stored_procedure():
    return finance_controller.execute_stored_procedure()


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
# AUTHENTICATION (ALL 4 ROLES)
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


# =====================================================================
# ROLE 0: SYSTEM ADMINISTRATOR
# =====================================================================
@app.route("/admin/health", methods=["GET"])
@app.route("/api/admin/health", methods=["GET"])
def admin_health():
    return admin_controller.get_system_health()


@app.route("/admin/thresholds", methods=["GET"])
@app.route("/api/admin/thresholds", methods=["GET"])
def admin_thresholds_get():
    return admin_controller.get_ai_thresholds()


@app.route("/admin/thresholds", methods=["POST", "PUT"])
@app.route("/api/admin/thresholds", methods=["POST", "PUT"])
def admin_thresholds_update():
    return admin_controller.update_ai_threshold()


@app.route("/admin/users", methods=["GET"])
@app.route("/api/admin/users", methods=["GET"])
def admin_users_list():
    return admin_controller.list_users()


@app.route("/admin/users/role", methods=["POST"])
@app.route("/api/admin/users/role", methods=["POST"])
def admin_user_role_update():
    return admin_controller.update_user_role()


@app.route("/admin/logs", methods=["GET"])
@app.route("/api/admin/logs", methods=["GET"])
def admin_logs():
    return admin_controller.get_system_logs()


# =====================================================================
# ROLE 1: ACCOUNTABLE OWNER / FINANCE ANALYST
# =====================================================================
@app.route("/analyst/tasks", methods=["GET"])
@app.route("/api/analyst/tasks", methods=["GET"])
def analyst_tasks():
    return analyst_controller.get_my_tasks()


@app.route("/analyst/sla-alerts", methods=["GET"])
@app.route("/api/analyst/sla-alerts", methods=["GET"])
def analyst_sla_alerts():
    return analyst_controller.get_sla_alerts()


@app.route("/analyst/insight/<int:exception_id>", methods=["GET"])
@app.route("/api/analyst/insight/<int:exception_id>", methods=["GET"])
def analyst_root_cause_insight(exception_id):
    return analyst_controller.get_root_cause_insight(exception_id)


@app.route("/analyst/action", methods=["POST"])
@app.route("/api/analyst/action", methods=["POST"])
def analyst_quick_action():
    return analyst_controller.submit_quick_action()


# =====================================================================
# ROLE 2: FINANCE LEADERSHIP / EXECUTIVE (CFO)
# =====================================================================
@app.route("/cfo/kpis", methods=["GET"])
@app.route("/api/cfo/kpis", methods=["GET"])
def cfo_kpis():
    return cfo_controller.get_financial_kpis()


@app.route("/cfo/early-warnings", methods=["GET"])
@app.route("/api/cfo/early-warnings", methods=["GET"])
def cfo_early_warnings():
    return cfo_controller.get_early_warnings()


@app.route("/cfo/escalated-risks", methods=["GET"])
@app.route("/api/cfo/escalated-risks", methods=["GET"])
def cfo_escalated_risks():
    return cfo_controller.get_escalated_risks()


@app.route("/cfo/executive-brief", methods=["GET"])
@app.route("/api/cfo/executive-brief", methods=["GET"])
def cfo_executive_brief():
    return cfo_controller.get_executive_brief()


# =====================================================================
# ROLE 3: AUDITOR / COMPLIANCE OFFICER
# =====================================================================
@app.route("/auditor/trail", methods=["GET"])
@app.route("/api/auditor/trail", methods=["GET"])
def auditor_trail():
    return auditor_controller.get_audit_trail()


@app.route("/auditor/sla-compliance", methods=["GET"])
@app.route("/api/auditor/sla-compliance", methods=["GET"])
def auditor_sla_compliance():
    return auditor_controller.get_sla_compliance()


@app.route("/auditor/hitl-metrics", methods=["GET"])
@app.route("/api/auditor/hitl-metrics", methods=["GET"])
def auditor_hitl_metrics():
    return auditor_controller.get_hitl_metrics()


@app.route("/auditor/export", methods=["GET"])
@app.route("/api/auditor/export", methods=["GET"])
def auditor_export():
    return auditor_controller.export_audit_records()


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    print(f"Starting FEMA on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)


