"""
services/finance_service.py
----------------------------
This file is the "brain" of FEMA. All real thinking/logic happens
here: calculating variance, deciding severity, picking a root cause,
assigning an owner, tracking SLA deadlines, escalating, building the
dashboard, and answering chatbot questions using RAG.

The controllers file (controllers/finance_controller.py) never does
math or database queries directly -- it just calls functions from
this file and returns whatever they give back.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

from sqlalchemy import text
from dbConnection.db import engine, get_session
from services.finance_models import Base, FinancialRecord, Owner, ExceptionCase, SystemThreshold

load_dotenv()

# =====================================================================
# DYNAMIC THRESHOLDS & RULE ENGINE (Loaded from MySQL DB)
# =====================================================================

DEFAULT_THRESHOLDS = [
    {
        "param_key": "variance_trigger_pct",
        "param_label": "Minimum Variance Trigger (%)",
        "param_value": "10.0",
        "param_type": "float",
        "description": "Minimum absolute variance % required to create an exception case.",
    },
    {
        "param_key": "severity_medium_threshold",
        "param_label": "Medium Severity Threshold (%)",
        "param_value": "20.0",
        "param_type": "float",
        "description": "Variance percentage threshold below which severity is MEDIUM.",
    },
    {
        "param_key": "severity_high_threshold",
        "param_label": "High Severity Threshold (%)",
        "param_value": "30.0",
        "param_type": "float",
        "description": "Variance percentage threshold below which severity is HIGH (above is CRITICAL).",
    },
    {
        "param_key": "sla_days_critical",
        "param_label": "CRITICAL SLA Resolution (Days)",
        "param_value": "1",
        "param_type": "int",
        "description": "Allowed business days to remediate a CRITICAL exception.",
    },
    {
        "param_key": "sla_days_high",
        "param_label": "HIGH SLA Resolution (Days)",
        "param_value": "3",
        "param_type": "int",
        "description": "Allowed business days to remediate a HIGH exception.",
    },
    {
        "param_key": "sla_days_medium",
        "param_label": "MEDIUM SLA Resolution (Days)",
        "param_value": "5",
        "param_type": "int",
        "description": "Allowed business days to remediate a MEDIUM exception.",
    },
    {
        "param_key": "sla_days_low",
        "param_label": "LOW SLA Resolution (Days)",
        "param_value": "7",
        "param_type": "int",
        "description": "Allowed business days to remediate a LOW exception.",
    },
    {
        "param_key": "min_level_critical",
        "param_label": "CRITICAL Minimum Owner Level",
        "param_value": "3",
        "param_type": "int",
        "description": "Minimum seniority level for CRITICAL exceptions (3 = Senior Finance Manager).",
    },
    {
        "param_key": "min_level_high",
        "param_label": "HIGH Minimum Owner Level",
        "param_value": "2",
        "param_type": "int",
        "description": "Minimum seniority level for HIGH exceptions (2 = Finance Manager).",
    },
    {
        "param_key": "min_level_medium_low",
        "param_label": "MEDIUM & LOW Minimum Owner Level",
        "param_value": "1",
        "param_type": "int",
        "description": "Minimum seniority level for MEDIUM & LOW exceptions (1 = Finance Executive).",
    },
]


def init_thresholds_db():
    """Ensures tables exist and columns are up to date."""
    try:
        Base.metadata.create_all(bind=engine)
        
        # Check and dynamically add missing columns to owners table if created with old schema
        with engine.connect() as conn:
            try:
                conn.execute(
                    text("ALTER TABLE owners ADD COLUMN department VARCHAR(100) DEFAULT 'General Finance'")
                )
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(
                    text("ALTER TABLE owners ADD COLUMN is_active INT DEFAULT 1")
                )
                conn.commit()
            except Exception:
                pass
            try:
                conn.execute(
                    text("ALTER TABLE owners ADD COLUMN max_approval_limit FLOAT DEFAULT 1000000.0")
                )
                conn.commit()
            except Exception:
                pass

        session = get_session()
        try:
            for item in DEFAULT_THRESHOLDS:
                existing = session.query(SystemThreshold).filter_by(param_key=item["param_key"]).first()
                if not existing:
                    new_param = SystemThreshold(
                        param_key=item["param_key"],
                        param_label=item["param_label"],
                        param_value=item["param_value"],
                        param_type=item["param_type"],
                        description=item["description"],
                        updated_by="system",
                    )
                    session.add(new_param)
            session.commit()
        except Exception as err:
            session.rollback()
            print(f"[init_thresholds_db] Seeding error: {err}")
        finally:
            session.close()
    except Exception as err:
        print(f"[init_thresholds_db] Table create warning: {err}")


def get_dynamic_thresholds(session=None) -> dict:
    """
    Dynamically loads detection and SLA parameters from MySQL DB.
    Falls back to safe defaults if table is unavailable.
    """
    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    params_dict = {}
    try:
        rows = session.query(SystemThreshold).all()
        for r in rows:
            params_dict[r.param_key] = r.param_value
    except Exception as err:
        print(f"[get_dynamic_thresholds] Falling back to default thresholds: {err}")
    finally:
        if close_session:
            session.close()

    def _get_float(key, default):
        try:
            return float(params_dict.get(key, default))
        except (ValueError, TypeError):
            return default

    def _get_int(key, default):
        try:
            return int(float(params_dict.get(key, default)))
        except (ValueError, TypeError):
            return default

    variance_trigger = _get_float("variance_trigger_pct", 10.0)
    medium_th = _get_float("severity_medium_threshold", 20.0)
    high_th = _get_float("severity_high_threshold", 30.0)

    sla_days = {
        "CRITICAL": _get_int("sla_days_critical", 1),
        "HIGH": _get_int("sla_days_high", 3),
        "MEDIUM": _get_int("sla_days_medium", 5),
        "LOW": _get_int("sla_days_low", 7),
    }

    min_levels = {
        "CRITICAL": _get_int("min_level_critical", 3),
        "HIGH": _get_int("min_level_high", 2),
        "MEDIUM": _get_int("min_level_medium_low", 1),
        "LOW": _get_int("min_level_medium_low", 1),
    }

    return {
        "variance_trigger": variance_trigger,
        "medium_threshold": medium_th,
        "high_threshold": high_th,
        "sla_days": sla_days,
        "min_levels": min_levels,
    }


# =====================================================================
# STEP: VARIANCE DETECTION
# =====================================================================
def calculate_variance(budget_amount: float, actual_amount: float) -> float:
    """
    Returns variance as a percentage.
    Formula: (Actual - Budget) / Budget * 100
    """
    if budget_amount == 0:
        return 100.0 if actual_amount != 0 else 0.0
    return ((actual_amount - budget_amount) / budget_amount) * 100.0


# =====================================================================
# STEP: SEVERITY CLASSIFICATION (Dynamic from DB Thresholds)
# =====================================================================
def classify_severity(variance_percent: float, thresholds: dict = None) -> str:
    """
    Dynamically decides severity based on configured DB thresholds:
    < medium_th -> LOW
    < high_th -> MEDIUM
    >= high_th -> CRITICAL (or HIGH if intermediate)
    """
    if thresholds is None:
        thresholds = get_dynamic_thresholds()

    magnitude = abs(variance_percent)
    medium_th = thresholds.get("medium_threshold", 20.0)
    high_th = thresholds.get("high_threshold", 30.0)

    if magnitude < medium_th:
        return "LOW"
    elif magnitude < high_th:
        return "HIGH" if (magnitude >= (medium_th + high_th) / 2) else "MEDIUM"
    else:
        return "CRITICAL"


# =====================================================================
# STEP: ROOT CAUSE ANALYSIS (100% Dynamic for ANY Category & Department)
# =====================================================================
def determine_root_cause(category: str, budget_amount: float, actual_amount: float,
                          variance_percent: float, department: str = None) -> str:
    """
    Dynamic, context-aware root cause generator supporting ANY financial category:
    (Revenue, Sales, Expense, CapEx, OpEx, COGS, Payroll, Cloud, Marketing, etc.)
    """
    direction = "under-budget / lower" if actual_amount < budget_amount else "over-budget / higher"
    cat_lower = (category or "").lower()
    dept_label = f" in {department}" if department else ""

    # Determine if category is typically inflow (income) or outflow (cost)
    is_inflow = any(w in cat_lower for w in ["rev", "sale", "income", "turnover", "billing", "receipt"])
    
    if is_inflow:
        if actual_amount < budget_amount:
            base_reason = f"Shortfall in {category}{dept_label} ({variance_percent:.1f}% below target): Likely client contract delay, deferred bookings, customer churn, or seasonal downturn."
        else:
            base_reason = f"Surplus in {category}{dept_label} (+{variance_percent:.1f}% above budget): Acceleration in closed deals, higher transaction volume, or one-off renewal expansion."
    elif any(w in cat_lower for w in ["cogs", "cost of goods", "inventory", "procurement"]):
        if actual_amount > budget_amount:
            base_reason = f"Cost inflation in {category}{dept_label} (+{variance_percent:.1f}% overrun): Raw material price surge, expediting freight fees, or unexpected supply chain tariff."
        else:
            base_reason = f"Favorable variance in {category}{dept_label} ({variance_percent:.1f}% below budget): Vendor discount realization or lower production run volumes."
    elif any(w in cat_lower for w in ["payroll", "salary", "comp", "benefit", "talent"]):
        if actual_amount > budget_amount:
            base_reason = f"Headcount / compensation variance in {category}{dept_label} (+{variance_percent:.1f}% overrun): Unplanned overtime, contractor surge, or off-cycle severance."
        else:
            base_reason = f"Hiring lag in {category}{dept_label} ({variance_percent:.1f}% below budget): Open positions unfilled or delayed start dates for budgeted requisitions."
    elif any(w in cat_lower for w in ["capex", "capital", "asset", "equipment", "hardware"]):
        if actual_amount > budget_amount:
            base_reason = f"CapEx escalation in {category}{dept_label} (+{variance_percent:.1f}% overrun): Accelerated infrastructure procurement, server hardware upgrades, or building build-out expenses."
        else:
            base_reason = f"Deferred capital project in {category}{dept_label} ({variance_percent:.1f}% under budget): Phased milestone delay or capital asset freeze."
    else:
        # General Expense / Other Categories
        if actual_amount > budget_amount:
            base_reason = f"Expenditure surge in {category}{dept_label} (+{variance_percent:.1f}% overrun): Unbudgeted departmental spend, vendor rate revision, or accelerated campaign execution."
        else:
            base_reason = f"Favorable expenditure in {category}{dept_label} ({variance_percent:.1f}% under budget): Operational belt-tightening or delayed vendor billing."

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return base_reason

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        prompt = (
            "You are a careful enterprise finance assistant. Using ONLY the data below, "
            "write ONE short, crisp sentence (max 25 words) proposing a plausible executive reason "
            "for this variance. Do not invent unstated facts.\n\n"
            f"Category: {category}\n"
            f"Department: {department or 'General'}\n"
            f"Budget: {budget_amount:,.2f}\n"
            f"Actual: {actual_amount:,.2f}\n"
            f"Variance: {variance_percent:+.2f}%\n"
            f"Rule-based hypothesis: {base_reason}\n"
        )
        response = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        llm_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()
        if llm_text:
            return f"{base_reason} (AI Note: {llm_text})"
    except Exception as error:
        print(f"[determine_root_cause] LLM enrichment skipped: {error}")

    return base_reason


# =====================================================================
# STEP: OWNER ASSIGNMENT (100% Dynamic Engine from DB)
# =====================================================================
def assign_owner(session, severity: str, department: str = None, thresholds: dict = None) -> Owner:
    """
    100% Dynamic, Zero-Hardcoded Owner Assignment:
    1. Determines minimum seniority level required from dynamic DB thresholds.
    2. Filters active owners matching the record's department (or 'All' / 'General Finance').
    3. If no department match, falls back to any qualified active owner.
    4. Applies Workload Balancing: picks candidate with the LOWEST active case count.
    """
    if thresholds is None:
        thresholds = get_dynamic_thresholds(session)

    min_level = thresholds["min_levels"].get(severity, 1)

    # Base candidate pool: active owners meeting minimum level
    candidates = (
        session.query(Owner)
        .filter(Owner.is_active == 1, Owner.level >= min_level)
        .all()
    )

    if not candidates:
        # Fallback to any active owner if level requirement has no active records
        candidates = session.query(Owner).filter(Owner.is_active == 1).all()

    if not candidates:
        # Absolute fallback if table has no active flags set
        return session.query(Owner).first()

    # Department affinity matching (case-insensitive substring match)
    matched_candidates = []
    if department:
        dept_clean = department.strip().lower()
        for cand in candidates:
            owner_dept = (cand.department or "").strip().lower()
            if (
                owner_dept == dept_clean
                or owner_dept in dept_clean
                or dept_clean in owner_dept
                or owner_dept in ["all", "general finance"]
            ):
                matched_candidates.append(cand)

    pool = matched_candidates if matched_candidates else candidates

    # Workload Balancing: count active open cases for each candidate
    best_owner = None
    min_workload = float("inf")

    for cand in pool:
        open_count = (
            session.query(ExceptionCase)
            .filter(
                ExceptionCase.owner_id == cand.id,
                ExceptionCase.status.in_(["OPEN", "IN_PROGRESS", "ESCALATED"]),
            )
            .count()
        )
        if open_count < min_workload:
            min_workload = open_count
            best_owner = cand
        elif open_count == min_workload and best_owner:
            # Tie breaker: choose the one closest to required seniority level
            if cand.level < best_owner.level:
                best_owner = cand

    return best_owner or pool[0]


# =====================================================================
# STEP: SLA TRACKING (Dynamic from DB Thresholds)
# =====================================================================
def calculate_sla_deadline(severity: str, thresholds: dict = None) -> datetime:
    """Returns the datetime by which this case must be resolved using dynamic DB days."""
    if thresholds is None:
        thresholds = get_dynamic_thresholds()

    days = thresholds["sla_days"].get(severity, 5)
    return datetime.utcnow() + timedelta(days=days)


# =====================================================================
# FINANCIAL RECORDS
# =====================================================================
def add_financial_record(data: dict) -> dict:
    """Saves a new Budget vs Actual entry."""
    session = get_session()
    try:
        record = FinancialRecord(
            category=data["category"],
            period=data["period"],
            department=data.get("department"),
            budget_amount=float(data["budget_amount"]),
            actual_amount=float(data["actual_amount"]),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record.to_dict()
    finally:
        session.close()


def get_all_financial_records() -> list:
    """Returns all financial records."""
    session = get_session()
    try:
        records = session.query(FinancialRecord).order_by(FinancialRecord.id.desc()).all()
        return [r.to_dict() for r in records]
    finally:
        session.close()


# =====================================================================
# MONITORING + EXCEPTION DETECTION (the core FEMA workflow)
# =====================================================================
def run_monitoring() -> dict:
    """
    Finds unprocessed financial records, calculates variance,
    and creates exception cases.
    """
    session = get_session()
    try:
        processed_ids = {
            r[0] for r in session.query(ExceptionCase.financial_record_id).all()
        }
        unprocessed = (
            session.query(FinancialRecord)
            .filter(~FinancialRecord.id.in_(processed_ids))
            .order_by(FinancialRecord.id.asc())
            .all()
        )

        thresholds = get_dynamic_thresholds(session)
        trigger_pct = thresholds.get("variance_trigger", 10.0)

        created = []
        for record in unprocessed:
            variance = calculate_variance(record.budget_amount, record.actual_amount)

            if abs(variance) < trigger_pct:
                continue

            severity = classify_severity(variance, thresholds)
            reason = determine_root_cause(
                record.category, record.budget_amount, record.actual_amount, variance, department=record.department
            )
            owner = assign_owner(session, severity, department=record.department, thresholds=thresholds)
            deadline = calculate_sla_deadline(severity, thresholds)

            new_case = ExceptionCase(
                financial_record_id=record.id,
                variance_percent=round(variance, 2),
                severity=severity,
                possible_reason=reason,
                status="OPEN",
                owner_id=owner.id if owner else None,
                sla_deadline=deadline,
                escalation_level=0,
            )
            session.add(new_case)
            session.flush()
            session.refresh(new_case)
            created.append(new_case.to_dict())

        session.commit()
        return {
            "records_checked": len(unprocessed),
            "exceptions_created": len(created),
            "new_exceptions": created,
        }
    finally:
        session.close()


# =====================================================================
# EXCEPTION CASES: READ / UPDATE / ESCALATE
# =====================================================================
def get_exceptions(severity: str = None, status: str = None) -> list:
    """Returns exception cases."""
    session = get_session()
    try:
        query = session.query(ExceptionCase).order_by(ExceptionCase.id.desc())
        if severity:
            query = query.filter(ExceptionCase.severity == severity.upper())
        if status:
            query = query.filter(ExceptionCase.status == status.upper())
        return [c.to_dict() for c in query.all()]
    finally:
        session.close()


def get_exception_by_id(exception_id: int):
    """Returns full detail of a single exception case."""
    session = get_session()
    try:
        case = session.query(ExceptionCase).filter(ExceptionCase.id == exception_id).first()
        return case.to_dict() if case else None
    finally:
        session.close()


def get_overdue_exceptions() -> list:
    """Cases whose SLA deadline has already passed AND are not yet resolved."""
    session = get_session()
    try:
        now = datetime.utcnow()
        cases = (
            session.query(ExceptionCase)
            .filter(
                ExceptionCase.sla_deadline < now,
                ExceptionCase.status != "RESOLVED",
            )
            .order_by(ExceptionCase.sla_deadline.asc())
            .all()
        )
        return [c.to_dict() for c in cases]
    finally:
        session.close()


def update_exception(exception_id: int, data: dict):
    """Updates status, owner, or possible reason."""
    session = get_session()
    try:
        case = session.query(ExceptionCase).filter(ExceptionCase.id == exception_id).first()
        if not case:
            return None

        if "status" in data and data["status"]:
            case.status = data["status"].upper()
        if "owner_id" in data and data["owner_id"] is not None:
            case.owner_id = int(data["owner_id"])
        if "possible_reason" in data and data["possible_reason"] is not None:
            case.possible_reason = data["possible_reason"]

        session.commit()
        session.refresh(case)
        return case.to_dict()
    finally:
        session.close()


def escalate_exception(exception_id: int):
    """
    100% Dynamic Escalation:
    Finds the next senior active owner (level > current owner's level) from MySQL,
    preferring department affinity or general executive management.
    """
    session = get_session()
    try:
        case = session.query(ExceptionCase).filter(ExceptionCase.id == exception_id).first()
        if not case:
            return None

        current_owner = session.query(Owner).filter(Owner.id == case.owner_id).first()
        current_level = current_owner.level if current_owner else (case.escalation_level or 1)

        # Query all active owners with a strictly higher seniority level
        next_candidates = (
            session.query(Owner)
            .filter(Owner.is_active == 1, Owner.level > current_level)
            .order_by(Owner.level.asc(), Owner.id.asc())
            .all()
        )

        if next_candidates:
            # Department preference for escalation
            record = session.query(FinancialRecord).filter(FinancialRecord.id == case.financial_record_id).first()
            rec_dept = (record.department or "").strip().lower() if record else ""

            best_escalated = next_candidates[0]
            for cand in next_candidates:
                cand_dept = (cand.department or "").strip().lower()
                if cand_dept == rec_dept or cand_dept in ["all", "general finance"]:
                    best_escalated = cand
                    break

            case.owner_id = best_escalated.id
            case.escalation_level = best_escalated.level
        else:
            case.escalation_level = (case.escalation_level or current_level) + 1

        case.status = "ESCALATED"
        session.commit()
        session.refresh(case)
        return case.to_dict()
    finally:
        session.close()


# =====================================================================
# DASHBOARD
# =====================================================================
def get_dashboard_summary() -> dict:
    """Returns summary numbers for dashboard."""
    session = get_session()
    try:
        total_records = session.query(FinancialRecord).count()
        exceptions = session.query(ExceptionCase).all()

        by_severity = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        by_status = {"OPEN": 0, "IN_PROGRESS": 0, "RESOLVED": 0, "ESCALATED": 0}
        overdue_count = 0
        now = datetime.utcnow()

        for c in exceptions:
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1
            by_status[c.status] = by_status.get(c.status, 0) + 1
            if c.sla_deadline and c.sla_deadline < now and c.status != "RESOLVED":
                overdue_count += 1

        return {
            "total_financial_records": total_records,
            "total_exceptions": len(exceptions),
            "exceptions_by_severity": by_severity,
            "exceptions_by_status": by_status,
            "overdue_exceptions": overdue_count,
        }
    finally:
        session.close()


# =====================================================================
# RAG FINANCE CHATBOT (ChromaDB + LLM)
# =====================================================================
_chroma_client = None
_chroma_collection = None


def _get_chroma_collection():
    """Lazily creates (or re-opens) our ChromaDB collection."""
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    import chromadb
    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_store")
    _chroma_client = chromadb.PersistentClient(path=persist_dir)
    _chroma_collection = _chroma_client.get_or_create_collection(name="fema_knowledge")
    return _chroma_collection


def sync_chroma_from_db():
    """
    Reads financial records and exception cases, formats them as context,
    and updates ChromaDB.
    """
    collection = _get_chroma_collection()
    documents = []
    ids = []

    records = get_all_financial_records()
    for r in records:
        variance = calculate_variance(r["budget_amount"], r["actual_amount"])
        text = (
            f"Financial record #{r['id']}: category={r['category']}, period={r['period']}, "
            f"department={r['department'] or 'N/A'}, budget={r['budget_amount']}, "
            f"actual={r['actual_amount']}, variance={variance:.2f}%."
        )
        documents.append(text)
        ids.append(f"record_{r['id']}")

    exceptions = get_exceptions()
    for e in exceptions:
        owner_name = e["owner"]["name"] if e.get("owner") else "Unassigned"
        text = (
            f"Exception case #{e['id']}: linked to financial record #{e['financial_record_id']}, "
            f"variance={e['variance_percent']}%, severity={e['severity']}, status={e['status']}, "
            f"owner={owner_name}, possible reason: {e.get('possible_reason')}, "
            f"SLA deadline={e.get('sla_deadline')}, escalation_level={e.get('escalation_level', 0)}."
        )
        documents.append(text)
        ids.append(f"exception_{e['id']}")

    if documents:
        collection.upsert(documents=documents, ids=ids)

    return {"synced_documents": len(documents)}


def chat_with_rag(question: str) -> dict:
    """
    Answers a user's question using RAG.
    """
    sync_chroma_from_db()
    collection = _get_chroma_collection()

    count = collection.count()
    if count == 0:
        return {
            "answer": "This information was not found in FEMA data (no financial records exist yet).",
            "sources": [],
        }

    results = collection.query(query_texts=[question], n_results=min(5, count))
    retrieved_docs = results.get("documents", [[]])[0]
    retrieved_ids = results.get("ids", [[]])[0]

    if not retrieved_docs:
        return {
            "answer": "This information was not found in FEMA data.",
            "sources": [],
        }

    context_text = "\n".join(f"- {doc}" for doc in retrieved_docs)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return {
            "answer": (
                "(No LLM key configured, showing raw matching FEMA data instead.)\n"
                + context_text
            ),
            "sources": retrieved_ids,
        }

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

        system_prompt = (
            "You are FEMA's finance assistant. Answer the user's question using "
            "ONLY the FEMA context provided below. Never invent numbers or facts "
            "that are not in the context. If the context does not contain the "
            "answer, reply exactly: 'This information was not found in FEMA data.'"
        )
        user_prompt = f"FEMA Context:\n{context_text}\n\nQuestion: {question}"

        response = client.messages.create(
            model=model,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        answer_text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        return {"answer": answer_text or "This information was not found in FEMA data.",
                "sources": retrieved_ids}
    except Exception as error:
        return {
            "answer": (
                f"(LLM call failed: {error}). Showing raw matching FEMA data instead.\n"
                + context_text
            ),
            "sources": retrieved_ids,
        }


# =====================================================================
# DYNAMIC OWNERS MANAGEMENT
# =====================================================================
def get_all_owners() -> list:
    """Returns all active and inactive owners with their current open workload count."""
    session = get_session()
    try:
        owners = session.query(Owner).order_by(Owner.level.asc(), Owner.name.asc()).all()
        result = []
        for o in owners:
            data = o.to_dict()
            open_cases = (
                session.query(ExceptionCase)
                .filter(
                    ExceptionCase.owner_id == o.id,
                    ExceptionCase.status.in_(["OPEN", "IN_PROGRESS", "ESCALATED"]),
                )
                .count()
            )
            data["active_cases"] = open_cases
            result.append(data)
        return result
    finally:
        session.close()


def add_owner(data: dict) -> dict:
    """Creates a new dynamic owner in the database."""
    session = get_session()
    try:
        owner = Owner(
            name=data["name"],
            email=data.get("email"),
            role=data["role"],
            level=int(data.get("level", 1)),
            department=data.get("department", "General Finance"),
            is_active=int(data.get("is_active", 1)),
            max_approval_limit=float(data.get("max_approval_limit", 1000000.0)),
        )
        session.add(owner)
        session.commit()
        session.refresh(owner)
        return owner.to_dict()
    finally:
        session.close()


