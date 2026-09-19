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

from dbConnection.db import get_session
from models.finance_models import FinancialRecord, Owner, ExceptionCase

load_dotenv()

# =====================================================================
# CONFIGURATION (easy to tweak without touching the logic below)
# =====================================================================

# Severity is decided using the ABSOLUTE variance percentage.
# <10% -> LOW, 10-20% -> MEDIUM, 20-30% -> HIGH, >30% -> CRITICAL
SEVERITY_RULES = [
    (10, "LOW"),
    (20, "MEDIUM"),
    (30, "HIGH"),
]
DEFAULT_SEVERITY = "CRITICAL"  # used when variance is above every rule above

# How many days an owner has to fix an exception, based on severity.
SLA_DAYS = {
    "LOW": 7,
    "MEDIUM": 5,
    "HIGH": 3,
    "CRITICAL": 1,
}

# Which role should first own a case of a given severity.
OWNER_ROLE_FOR_SEVERITY = {
    "LOW": "Finance Executive",
    "MEDIUM": "Finance Executive",
    "HIGH": "Finance Manager",
    "CRITICAL": "Senior Finance Manager",
}

# The order roles get escalated through, lowest -> highest.
ESCALATION_ORDER = [
    "Finance Executive",
    "Finance Manager",
    "Senior Finance Manager",
    "CFO",
]

# Simple, rule-based "why did this happen" explanations.
# Key = (category, direction), Value = plain-English possible reason.
ROOT_CAUSE_RULES = {
    ("Revenue", "decrease"): "Possible drop in sales, lost customers, delayed customer payments, or a slow market.",
    ("Revenue", "increase"): "Possible higher sales, new customers won, or a one-time bulk order.",
    ("Expense", "increase"): "Possible cost overrun, unplanned purchases, price hikes from vendors, or inefficiency.",
    ("Expense", "decrease"): "Possible cost-saving measures, delayed spending, or under-utilised budget.",
}
DEFAULT_ROOT_CAUSE = "Reason not clear from simple rules -- needs manual review by the assigned owner."


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
# STEP: SEVERITY CLASSIFICATION
# =====================================================================
def classify_severity(variance_percent: float) -> str:
    """
    Looks at the SIZE of the variance (ignoring +/- sign) and decides
    how serious it is, using the SEVERITY_RULES table above.
    """
    magnitude = abs(variance_percent)
    for threshold, severity in SEVERITY_RULES:
        if magnitude < threshold:
            return severity
    return DEFAULT_SEVERITY


# =====================================================================
# STEP: ROOT CAUSE ANALYSIS
# =====================================================================
def determine_root_cause(category: str, budget_amount: float, actual_amount: float,
                          variance_percent: float) -> str:
    """
    Rule-based first guess at "why did this happen".
    """
    direction = "decrease" if actual_amount < budget_amount else "increase"
    base_reason = ROOT_CAUSE_RULES.get((category, direction), DEFAULT_ROOT_CAUSE)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return base_reason

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        prompt = (
            "You are a careful finance assistant. Using ONLY the numbers below, "
            "write ONE short sentence (max 25 words) suggesting a plausible reason "
            "for this variance. Do not invent company facts you were not given.\n\n"
            f"Category: {category}\n"
            f"Budget Amount: {budget_amount}\n"
            f"Actual Amount: {actual_amount}\n"
            f"Variance: {variance_percent:.2f}%\n"
            f"Rule-based hint: {base_reason}\n"
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
            return f"{base_reason} (AI note: {llm_text})"
    except Exception as error:
        print(f"[determine_root_cause] LLM enrichment skipped: {error}")

    return base_reason


# =====================================================================
# STEP: OWNER ASSIGNMENT
# =====================================================================
def assign_owner(session, severity: str) -> Owner:
    """
    Picks the right person to own a case, based on severity.
    """
    role_needed = OWNER_ROLE_FOR_SEVERITY.get(severity, "Finance Executive")
    owner = session.query(Owner).filter(Owner.role == role_needed).first()
    if owner is None:
        owner = session.query(Owner).order_by(Owner.level.asc()).first()
    return owner


# =====================================================================
# STEP: SLA TRACKING
# =====================================================================
def calculate_sla_deadline(severity: str) -> datetime:
    """Returns the datetime by which this case must be resolved."""
    days = SLA_DAYS.get(severity, 5)
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

        created = []
        for record in unprocessed:
            variance = calculate_variance(record.budget_amount, record.actual_amount)

            if abs(variance) < 10:
                continue

            severity = classify_severity(variance)
            reason = determine_root_cause(
                record.category, record.budget_amount, record.actual_amount, variance
            )
            owner = assign_owner(session, severity)
            deadline = calculate_sla_deadline(severity)

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
    """Bumps case to next senior owner and marks ESCALATED."""
    session = get_session()
    try:
        case = session.query(ExceptionCase).filter(ExceptionCase.id == exception_id).first()
        if not case:
            return None

        current_level = case.escalation_level or 0
        next_level = min(current_level + 1, len(ESCALATION_ORDER) - 1)
        next_role = ESCALATION_ORDER[next_level]

        next_owner = session.query(Owner).filter(Owner.role == next_role).first()
        if next_owner:
            case.owner_id = next_owner.id
        case.escalation_level = next_level
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

