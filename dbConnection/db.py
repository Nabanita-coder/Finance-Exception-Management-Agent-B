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


def init_db():
    """
    Creates all tables in MySQL if they don't already exist,
    and adds a few starter Owners so the app has someone to
    assign cases to right from the start.

    This is called once when the Flask app starts (see app.py).
    """
    # 1. Ensure the MySQL database itself exists
    server_url = f"mysql+pymysql://{DB_USER}:{SAFE_PASSWORD}@{DB_HOST}:{DB_PORT}"
    server_engine = create_engine(server_url, pool_pre_ping=True)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))
        conn.commit()
    server_engine.dispose()

    # 2. This looks at every class above (Owner, FinancialRecord, ExceptionCase)
    # and creates a matching table in MySQL if it isn't there yet.
    Base.metadata.create_all(bind=engine)

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
