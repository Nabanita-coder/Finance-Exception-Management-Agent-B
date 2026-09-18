-- ============================================================
-- schema.sql
-- ------------------------------------------------------------
-- This file is ONLY for reference / viewing in MySQL Workbench.
-- You do NOT need to run this by hand -- when you start the app
-- with "python app.py", SQLAlchemy (dbConnection/db.py) creates
-- these same tables for you automatically.
--
-- If you'd like to create them manually in Workbench instead,
-- just run this whole script.
-- ============================================================

CREATE DATABASE IF NOT EXISTS fema_db;
USE fema_db;

-- Table 1: Owners (the people who fix exception cases)
CREATE TABLE IF NOT EXISTS owners (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120),
    role VARCHAR(50) NOT NULL,   -- Finance Executive / Finance Manager / Senior Finance Manager / CFO
    level INT NOT NULL           -- 1 = lowest seniority, 4 = highest (CFO)
);

-- Table 2: Financial Records (budget vs actual numbers)
CREATE TABLE IF NOT EXISTS financial_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50) NOT NULL,      -- e.g. Revenue, Expense
    period VARCHAR(20) NOT NULL,        -- e.g. 2026-09
    department VARCHAR(100),
    budget_amount FLOAT NOT NULL,
    actual_amount FLOAT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Exception Cases (the "case files" FEMA creates)
CREATE TABLE IF NOT EXISTS exception_cases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    financial_record_id INT NOT NULL,
    variance_percent FLOAT NOT NULL,
    severity VARCHAR(20) NOT NULL,           -- LOW / MEDIUM / HIGH / CRITICAL
    possible_reason TEXT,
    status VARCHAR(20) DEFAULT 'OPEN',       -- OPEN / IN_PROGRESS / RESOLVED / ESCALATED
    owner_id INT,
    sla_deadline DATETIME,
    escalation_level INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (financial_record_id) REFERENCES financial_records(id),
    FOREIGN KEY (owner_id) REFERENCES owners(id)
);

-- Starter owners (app.py also does this automatically on first run)
INSERT INTO owners (name, email, role, level) VALUES
    ('Asha Verma', 'asha@company.com', 'Finance Executive', 1),
    ('Rohit Sharma', 'rohit@company.com', 'Finance Manager', 2),
    ('Neha Kapoor', 'neha@company.com', 'Senior Finance Manager', 3),
    ('CFO Office', 'cfo@company.com', 'CFO', 4);
