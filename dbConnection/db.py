"""
dbConnection/db.py
-------------------
This file is the "pipe" that connects our FEMA application to the
MySQL database (fema_db).

What this file does:
1. Reads database settings from the .env file.
2. Opens a connection to MySQL using SQLAlchemy.
3. Defines the shape of our 3 tables (Owner, FinancialRecord, ExceptionCase)
   as Python classes. SQLAlchemy turns these classes into real MySQL tables.
4. Gives other files (services/controllers) an easy way to talk to the database.

Think of the classes below as "forms" that describe what columns each
table has. SQLAlchemy reads these forms and creates matching tables in
MySQL automatically the first time the app runs.
"""

import os
from datetime import datetime
from urllib.parse import quote_plus

from dotenv import load_dotenv
import pymysql
import pymysql.cursors
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Load variables from the .env file into the environment
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "fema_db")

# Automatically encodes '@', '#', '%', etc. so passwords like Root@123 work properly
SAFE_PASSWORD = quote_plus(DB_PASSWORD) if DB_PASSWORD else ""

# This is the connection string SQLAlchemy uses to reach MySQL.
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{SAFE_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# The "engine" is the actual live connection manager to MySQL.
# pool_pre_ping=True makes sure dead connections are refreshed automatically.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

# A "Session" is like a temporary workspace/notepad we use to read and
# write data. SessionLocal() gives us a new notepad whenever we need one.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base is the parent class that all our table classes will inherit from.
Base = declarative_base()


# =========================================================
# TABLE 1: Owners
# The people who are responsible for fixing exception cases.
# =========================================================
class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120))
    # e.g. "Finance Executive", "Finance Manager", "Senior Finance Manager", "CFO"
    role = Column(String(50), nullable=False)
    # A number showing seniority: 1 = lowest, 4 = highest (CFO).
    # Used when we escalate a case to the next senior person.
    level = Column(Integer, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "level": self.level,
        }


# =========================================================
# TABLE 2: Financial Records
# The raw budget vs actual numbers we monitor.
# =========================================================
class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # e.g. "Revenue", "Expense", "Marketing Spend", "Operating Cost"
    category = Column(String(50), nullable=False)
    # e.g. "2026-09" (which month/period this record belongs to)
    period = Column(String(20), nullable=False)
    department = Column(String(100))
    budget_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "period": self.period,
            "department": self.department,
            "budget_amount": self.budget_amount,
            "actual_amount": self.actual_amount,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================
# TABLE 3: Exception Cases
# The "case files" FEMA opens when it finds something unusual.
# =========================================================
class ExceptionCase(Base):
    __tablename__ = "exception_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    financial_record_id = Column(
        Integer, ForeignKey("financial_records.id"), nullable=False
    )
    variance_percent = Column(Float, nullable=False)
    # LOW / MEDIUM / HIGH / CRITICAL
    severity = Column(String(20), nullable=False)
    possible_reason = Column(Text)
    # OPEN / IN_PROGRESS / RESOLVED / ESCALATED
    status = Column(String(20), default="OPEN")
    owner_id = Column(Integer, ForeignKey("owners.id"))
    sla_deadline = Column(DateTime)
    # How many times this case has been escalated (0 = never escalated)
    escalation_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # These let us easily access the related record/owner in Python,
    # e.g. exception.owner.name or exception.financial_record.category
    financial_record = relationship("FinancialRecord")
    owner = relationship("Owner")

    def to_dict(self):
        return {
            "id": self.id,
            "financial_record_id": self.financial_record_id,
            "financial_record": self.financial_record.to_dict()
            if self.financial_record else None,
            "variance_percent": self.variance_percent,
            "severity": self.severity,
            "possible_reason": self.possible_reason,
            "status": self.status,
            "owner": self.owner.to_dict() if self.owner else None,
            "sla_deadline": self.sla_deadline.isoformat() if self.sla_deadline else None,
            "escalation_level": self.escalation_level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def get_session():
    """
    Gives you a fresh SQLAlchemy session (a 'workspace') to run
    database operations in. Always close it when you're done
    (services use a 'with' style helper below for safety).
    """
    return SessionLocal()


def get_raw_connection():
    """Returns a direct PyMySQL connection configured for dict cursors."""
    return pymysql.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


def call_sp(proc_name: str, params: list = None) -> list:
    """
    Executes a MySQL Stored Procedure and returns result rows as a list of dicts.
    Handles procedures that have multiple internal statements / nested calls.
    """
    if params is None:
        params = []
    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            cursor.callproc(proc_name, params)
            results = cursor.fetchall()
            while cursor.nextset():
                extra = cursor.fetchall()
                if extra:
                    results = extra
            return list(results or [])
    finally:
        conn.close()


def call_sp_single(proc_name: str, params: list = None) -> dict:
    """Executes a Stored Procedure and returns the first row, or None."""
    rows = call_sp(proc_name, params)
    return rows[0] if rows else None


def format_record_row(row: dict) -> dict:
    """Normalizes a raw financial_records row into clean API output format."""
    if not row:
        return None
    created_at = row.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "period": row.get("period"),
        "department": row.get("department"),
        "budget_amount": float(row.get("budget_amount", 0)),
        "actual_amount": float(row.get("actual_amount", 0)),
        "created_at": created_at,
    }


def format_exception_row(row: dict) -> dict:
    """Normalizes a joined exception_cases row into the standard API structure."""
    if not row:
        return None

    created_at = row.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    updated_at = row.get("updated_at")
    if hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()

    sla_deadline = row.get("sla_deadline")
    if hasattr(sla_deadline, "isoformat"):
        sla_deadline = sla_deadline.isoformat()

    rec_created_at = row.get("record_created_at")
    if hasattr(rec_created_at, "isoformat"):
        rec_created_at = rec_created_at.isoformat()

    financial_record = None
    if row.get("financial_record_id"):
        financial_record = {
            "id": row["financial_record_id"],
            "category": row.get("record_category"),
            "period": row.get("record_period"),
            "department": row.get("record_department"),
            "budget_amount": float(row.get("record_budget", 0)) if row.get("record_budget") is not None else 0.0,
            "actual_amount": float(row.get("record_actual", 0)) if row.get("record_actual") is not None else 0.0,
            "created_at": rec_created_at,
        }

    owner = None
    if row.get("owner_id"):
        owner = {
            "id": row["owner_id"],
            "name": row.get("owner_name"),
            "email": row.get("owner_email"),
            "role": row.get("owner_role"),
            "level": row.get("owner_level"),
        }

    return {
        "id": row.get("id"),
        "financial_record_id": row.get("financial_record_id"),
        "financial_record": financial_record,
        "variance_percent": float(row.get("variance_percent", 0)),
        "severity": row.get("severity"),
        "possible_reason": row.get("possible_reason"),
        "status": row.get("status"),
        "owner": owner,
        "sla_deadline": sla_deadline,
        "escalation_level": row.get("escalation_level", 0),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def init_stored_procedures():
    """
    Reads dbConnection/stored_procedures.sql and creates/updates
    all Stored Procedures in MySQL.
    """
    sp_file = os.path.join(os.path.dirname(__file__), "stored_procedures.sql")
    if not os.path.exists(sp_file):
        return

    with open(sp_file, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split("-- PROCEDURE_DELIMITER")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            for block in blocks:
                cleaned = "\n".join(
                    line for line in block.splitlines() if not line.strip().startswith("--")
                ).strip()
                if cleaned:
                    cursor.execute(cleaned)
        print("Stored procedures loaded and registered into MySQL.")
    finally:
        conn.close()


def init_db():
    """
    Creates all tables in MySQL if they don't already exist,
    adds starter Owners, and compiles all Stored Procedures.

    This is called once when the Flask app starts (see app.py).
    """
    # 1. Ensure the MySQL database itself exists
    server_url = f"mysql+pymysql://{DB_USER}:{SAFE_PASSWORD}@{DB_HOST}:{DB_PORT}"
    server_engine = create_engine(server_url, pool_pre_ping=True)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))
        conn.commit()
    server_engine.dispose()

    # 2. Creates matching tables in MySQL if not there yet
    Base.metadata.create_all(bind=engine)

    # 3. Seed starter owners
    session = get_session()
    try:
        existing_owners = session.query(Owner).count()
        if existing_owners == 0:
            starter_owners = [
                Owner(name="Asha Verma", email="asha@company.com",
                      role="Finance Executive", level=1),
                Owner(name="Rohit Sharma", email="rohit@company.com",
                      role="Finance Manager", level=2),
                Owner(name="Neha Kapoor", email="neha@company.com",
                      role="Senior Finance Manager", level=3),
                Owner(name="CFO Office", email="cfo@company.com",
                      role="CFO", level=4),
            ]
            session.add_all(starter_owners)
            session.commit()
            print("Seeded starter owners into the 'owners' table.")
    finally:
        session.close()

    # 4. Compile and register all Stored Procedures in MySQL
    init_stored_procedures()

