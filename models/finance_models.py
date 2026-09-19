"""
models/finance_models.py
-------------------------
SQLAlchemy ORM Models mapping to existing MySQL tables.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# =========================================================
# TABLE 1: Owners
# =========================================================
class Owner(Base):
    __tablename__ = "owners"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120))
    role = Column(String(50), nullable=False)
    level = Column(Integer, nullable=False)
    department = Column(String(100), default="General Finance")
    is_active = Column(Integer, default=1)
    max_approval_limit = Column(Float, default=1000000.0)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "level": self.level,
            "department": self.department,
            "is_active": self.is_active,
            "max_approval_limit": self.max_approval_limit,
        }


# =========================================================
# TABLE 2: Financial Records
# =========================================================
class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
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
            "variance_amount": self.actual_amount - self.budget_amount,
            "variance_percent": (
                ((self.actual_amount - self.budget_amount) / self.budget_amount) * 100.0
                if self.budget_amount != 0
                else 0.0
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =========================================================
# TABLE 3: Exception Cases
# =========================================================
class ExceptionCase(Base):
    __tablename__ = "exception_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    financial_record_id = Column(Integer, ForeignKey("financial_records.id"), nullable=False)
    variance_percent = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False)
    possible_reason = Column(Text)
    status = Column(String(20), default="OPEN")
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=True)
    sla_deadline = Column(DateTime, nullable=True)
    escalation_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    financial_record = relationship("FinancialRecord", lazy="joined")
    owner = relationship("Owner", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "financial_record_id": self.financial_record_id,
            "financial_record": self.financial_record.to_dict() if self.financial_record else None,
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
