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

from dbConnection.db import get_session, FinancialRecord, Owner, ExceptionCase

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

    Example: Budget=10,00,000 Actual=6,00,000 -> variance = -40.0
    A negative number means actual came in BELOW budget.
    A positive number means actual came in ABOVE budget.
    """
    if budget_amount == 0:
        # Avoid dividing by zero. Treat any actual amount as a huge swing.
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
    If an ANTHROPIC_API_KEY is configured, we also ask the LLM to phrase
    a short, careful explanation -- but it is told to reason ONLY from
    the numbers given, never to invent outside facts.
    """
    direction = "decrease" if actual_amount < budget_amount else "increase"
    base_reason = ROOT_CAUSE_RULES.get((category, direction), DEFAULT_ROOT_CAUSE)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        # No LLM configured -- just return the simple rule-based reason.
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
        # If the LLM call fails for any reason (bad key, no internet, etc.)
        # we simply fall back to the rule-based reason -- FEMA still works.
        print(f"[determine_root_cause] LLM enrichment skipped: {error}")

    return base_reason


# =====================================================================
# STEP: OWNER ASSIGNMENT
# =====================================================================
def assign_owner(session, severity: str) -> Owner:
    """
    Picks the right person to own a case, based on severity.
    LOW/MEDIUM -> Finance Executive
    HIGH       -> Finance Manager
    CRITICAL   -> Senior Finance Manager
    """
    role_needed = OWNER_ROLE_FOR_SEVERITY.get(severity, "Finance Executive")
    owner = session.query(Owner).filter(Owner.role == role_needed).first()
    if owner is None:
        # Fall back to whichever owner exists, so a case is never left unassigned.
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
    """Saves a new Budget vs Actual entry into MySQL."""
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
    Goes through every financial record that does NOT already have an
    exception case, calculates variance, and if it's unusual, creates
    a full exception case: severity + root cause + owner + SLA deadline.

    Returns a small summary of what happened.
    """
    session = get_session()
    created = []
    try:
        # Find records that don't already have an exception case.
        records_with_exceptions = {
            e.financial_record_id
            for e in session.query(ExceptionCase.financial_record_id).all()
        }
        all_records = session.query(FinancialRecord).all()
        records_to_check = [
            r for r in all_records if r.id not in records_with_exceptions
        ]

        for record in records_to_check:
            variance = calculate_variance(record.budget_amount, record.actual_amount)

            # Anything under 10% variance is considered normal -- no exception.
            if abs(variance) < 10:
                continue

            severity = classify_severity(variance)
            reason = determine_root_cause(
                record.category, record.budget_amount, record.actual_amount, variance
            )
            owner = assign_owner(session, severity)
            deadline = calculate_sla_deadline(severity)

            exception = ExceptionCase(
                financial_record_id=record.id,
                variance_percent=round(variance, 2),
                severity=severity,
                possible_reason=reason,
                status="OPEN",
                owner_id=owner.id if owner else None,
                sla_deadline=deadline,
                escalation_level=0,
            )
            session.add(exception)
            session.commit()
            session.refresh(exception)
            created.append(exception.to_dict())

        return {
            "records_checked": len(records_to_check),
            "exceptions_created": len(created),
            "new_exceptions": created,
        }
    finally:
        session.close()


# =====================================================================
# EXCEPTION CASES: READ / UPDATE / ESCALATE
# =====================================================================
def get_exceptions(severity: str = None, status: str = None) -> list:
    session = get_session()
    try:
        query = session.query(ExceptionCase)
        if severity:
            query = query.filter(ExceptionCase.severity == severity.upper())
        if status:
            query = query.filter(ExceptionCase.status == status.upper())
        results = query.order_by(ExceptionCase.id.desc()).all()
        return [e.to_dict() for e in results]
    finally:
        session.close()


def get_exception_by_id(exception_id: int):
    session = get_session()
    try:
        exception = session.query(ExceptionCase).get(exception_id)
        return exception.to_dict() if exception else None
    finally:
        session.close()


def get_overdue_exceptions() -> list:
    """Cases whose SLA deadline has already passed AND are not yet resolved."""
    session = get_session()
    try:
        now = datetime.utcnow()
        results = (
            session.query(ExceptionCase)
            .filter(ExceptionCase.sla_deadline < now)
            .filter(ExceptionCase.status != "RESOLVED")
            .order_by(ExceptionCase.sla_deadline.asc())
            .all()
        )
        return [e.to_dict() for e in results]
    finally:
        session.close()


def update_exception(exception_id: int, data: dict):
    """
    Lets a user update a case -- typically its status
    (e.g. move from OPEN -> IN_PROGRESS -> RESOLVED) or reassign it
    to a different owner.
    """
    session = get_session()
    try:
        exception = session.query(ExceptionCase).get(exception_id)
        if exception is None:
            return None

        if "status" in data:
            exception.status = data["status"].upper()
        if "owner_id" in data:
            exception.owner_id = data["owner_id"]
        if "possible_reason" in data:
            exception.possible_reason = data["possible_reason"]

        exception.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(exception)
        return exception.to_dict()
    finally:
        session.close()


def escalate_exception(exception_id: int):
    """
    Bumps a case up to the next, more senior owner and marks it ESCALATED.
    Used when a case has breached its SLA deadline and is still unresolved.
    """
    session = get_session()
    try:
        exception = session.query(ExceptionCase).get(exception_id)
        if exception is None:
            return None

        current_role = exception.owner.role if exception.owner else ESCALATION_ORDER[0]
        try:
            current_index = ESCALATION_ORDER.index(current_role)
        except ValueError:
            current_index = 0

        next_index = min(current_index + 1, len(ESCALATION_ORDER) - 1)
        next_role = ESCALATION_ORDER[next_index]

        next_owner = session.query(Owner).filter(Owner.role == next_role).first()
        if next_owner:
            exception.owner_id = next_owner.id

        exception.escalation_level = (exception.escalation_level or 0) + 1
        exception.status = "ESCALATED"
        exception.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(exception)
        return exception.to_dict()
    finally:
        session.close()


# =====================================================================
# DASHBOARD
# =====================================================================
def get_dashboard_summary() -> dict:
    session = get_session()
    try:
        total_records = session.query(FinancialRecord).count()
        total_exceptions = session.query(ExceptionCase).count()

        by_severity = {}
        for severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            by_severity[severity] = (
                session.query(ExceptionCase)
                .filter(ExceptionCase.severity == severity)
                .count()
            )

        by_status = {}
        for status in ["OPEN", "IN_PROGRESS", "RESOLVED", "ESCALATED"]:
            by_status[status] = (
                session.query(ExceptionCase)
                .filter(ExceptionCase.status == status)
                .count()
            )

        overdue_count = len(get_overdue_exceptions())

        return {
            "total_financial_records": total_records,
            "total_exceptions": total_exceptions,
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
    """
    Lazily creates (or re-opens) our ChromaDB collection.
    ChromaDB stores text in a way that can be searched by MEANING,
    not just exact keywords -- this is what powers the chatbot's
    ability to find relevant facts.
    """
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
    Reads every financial record and exception case from MySQL,
    turns each one into a short paragraph of text, and stores it
    in ChromaDB so the chatbot can search over it later.

    Run this after adding records / running monitoring, so the
    chatbot always answers using fresh data.
    """
    collection = _get_chroma_collection()
    session = get_session()
    try:
        documents = []
        ids = []

        records = session.query(FinancialRecord).all()
        for r in records:
            variance = calculate_variance(r.budget_amount, r.actual_amount)
            text = (
                f"Financial record #{r.id}: category={r.category}, period={r.period}, "
                f"department={r.department or 'N/A'}, budget={r.budget_amount}, "
                f"actual={r.actual_amount}, variance={variance:.2f}%."
            )
            documents.append(text)
            ids.append(f"record_{r.id}")

        exceptions = session.query(ExceptionCase).all()
        for e in exceptions:
            owner_name = e.owner.name if e.owner else "Unassigned"
            text = (
                f"Exception case #{e.id}: linked to financial record #{e.financial_record_id}, "
                f"variance={e.variance_percent}%, severity={e.severity}, status={e.status}, "
                f"owner={owner_name}, possible reason: {e.possible_reason}, "
                f"SLA deadline={e.sla_deadline}, escalation_level={e.escalation_level}."
            )
            documents.append(text)
            ids.append(f"exception_{e.id}")

        if documents:
            # 'upsert' means: add new ones, and update ones that already exist.
            collection.upsert(documents=documents, ids=ids)

        return {"synced_documents": len(documents)}
    finally:
        session.close()


def chat_with_rag(question: str) -> dict:
    """
    Answers a user's question using RAG:
      1. RETRIEVE: search ChromaDB for the most relevant facts.
      2. AUGMENT + GENERATE: give those facts to the LLM and ask it
         to answer using ONLY that context.

    If nothing relevant is found, or no LLM is configured, FEMA
    clearly says the information was not found -- it never invents
    financial numbers.
    """
    # Make sure Chroma has the latest data before answering.
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
        # No LLM key configured -- just show the raw matching facts.
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
