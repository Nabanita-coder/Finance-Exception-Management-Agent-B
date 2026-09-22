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

-- Table 4: Roles (0 for Admin, 1 for User)
CREATE TABLE IF NOT EXISTS roles (
    id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Initial Roles (Option A: Consolidated 3 Roles)
INSERT IGNORE INTO roles (id, name, description) VALUES
    (0, 'admin', 'Admin & Compliance Officer - System health, AI thresholds, audit trail & SOX 404'),
    (1, 'analyst', 'Finance Analyst - Action-oriented queue, SLA alerts, AI insights & resolution'),
    (2, 'cfo', 'Finance Leadership / CFO - Strategic KPIs, early warnings, escalated risks');

-- Table 5: Users (application users with role-based access)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id INT NOT NULL DEFAULT 1,
    full_name VARCHAR(120),
    is_active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

-- Starter owners (app.py also does this automatically on first run)
INSERT IGNORE INTO owners (id, name, email, role, level) VALUES
    (1, 'Asha Verma', 'asha@company.com', 'Finance Executive', 1),
    (2, 'Rohit Sharma', 'rohit@company.com', 'Finance Manager', 2),
    (3, 'Neha Kapoor', 'neha@company.com', 'Senior Finance Manager', 3),
    (4, 'CFO Office', 'cfo@company.com', 'CFO', 4);

-- Table 6: AI Detection & System Thresholds (Dynamic Rules Engine)
CREATE TABLE IF NOT EXISTS ai_thresholds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    param_key VARCHAR(80) NOT NULL UNIQUE,
    param_label VARCHAR(120) NOT NULL,
    param_value VARCHAR(100) NOT NULL,
    param_type VARCHAR(30) DEFAULT 'float',
    description VARCHAR(255),
    updated_by VARCHAR(80) DEFAULT 'system',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO ai_thresholds (param_key, param_label, param_value, param_type, description) VALUES
    ('variance_trigger_pct', 'Minimum Variance Trigger (%)', '10.0', 'float', 'Minimum absolute variance % required to create an exception case.'),
    ('severity_medium_threshold', 'Medium Severity Threshold (%)', '20.0', 'float', 'Variance percentage threshold below which severity is MEDIUM.'),
    ('severity_high_threshold', 'High Severity Threshold (%)', '30.0', 'float', 'Variance percentage threshold below which severity is HIGH (above is CRITICAL).'),
    ('sla_days_critical', 'CRITICAL SLA Resolution (Days)', '1', 'int', 'Allowed business days to remediate a CRITICAL exception.'),
    ('sla_days_high', 'HIGH SLA Resolution (Days)', '3', 'int', 'Allowed business days to remediate a HIGH exception.'),
    ('sla_days_medium', 'MEDIUM SLA Resolution (Days)', '5', 'int', 'Allowed business days to remediate a MEDIUM exception.'),
    ('sla_days_low', 'LOW SLA Resolution (Days)', '7', 'int', 'Allowed business days to remediate a LOW exception.'),
    ('min_level_critical', 'CRITICAL Minimum Owner Level', '3', 'int', 'Minimum seniority level for CRITICAL exceptions (3 = Senior Finance Manager).'),
    ('min_level_high', 'HIGH Minimum Owner Level', '2', 'int', 'Minimum seniority level for HIGH exceptions (2 = Finance Manager).'),
    ('min_level_medium_low', 'MEDIUM & LOW Minimum Owner Level', '1', 'int', 'Minimum seniority level for MEDIUM & LOW exceptions (1 = Finance Executive).');

-- ============================================================
-- STORED PROCEDURES
-- ============================================================

DELIMITER $$

-- 1. Add Financial Record
DROP PROCEDURE IF EXISTS sp_add_financial_record$$
CREATE PROCEDURE sp_add_financial_record(
    IN p_category VARCHAR(50),
    IN p_period VARCHAR(20),
    IN p_department VARCHAR(100),
    IN p_budget_amount FLOAT,
    IN p_actual_amount FLOAT
)
BEGIN
    INSERT INTO financial_records (category, period, department, budget_amount, actual_amount, created_at)
    VALUES (p_category, p_period, p_department, p_budget_amount, p_actual_amount, NOW());

    SELECT id, category, period, department, budget_amount, actual_amount, created_at
    FROM financial_records
    WHERE id = LAST_INSERT_ID();
END$$

-- 2. Get All Financial Records
DROP PROCEDURE IF EXISTS sp_get_all_financial_records$$
CREATE PROCEDURE sp_get_all_financial_records()
BEGIN
    SELECT id, category, period, department, budget_amount, actual_amount, created_at
    FROM financial_records
    ORDER BY id DESC;
END$$

-- 3. Get Unprocessed Records (records without exception case)
DROP PROCEDURE IF EXISTS sp_get_unprocessed_financial_records$$
CREATE PROCEDURE sp_get_unprocessed_financial_records()
BEGIN
    SELECT fr.id, fr.category, fr.period, fr.department, fr.budget_amount, fr.actual_amount, fr.created_at
    FROM financial_records fr
    LEFT JOIN exception_cases ec ON fr.id = ec.financial_record_id
    WHERE ec.id IS NULL
    ORDER BY fr.id ASC;
END$$

-- 4. Create Exception Case
DROP PROCEDURE IF EXISTS sp_create_exception_case$$
CREATE PROCEDURE sp_create_exception_case(
    IN p_financial_record_id INT,
    IN p_variance_percent FLOAT,
    IN p_severity VARCHAR(20),
    IN p_possible_reason TEXT,
    IN p_owner_id INT,
    IN p_sla_deadline DATETIME
)
BEGIN
    INSERT INTO exception_cases (
        financial_record_id, variance_percent, severity,
        possible_reason, status, owner_id, sla_deadline,
        escalation_level, created_at, updated_at
    )
    VALUES (
        p_financial_record_id, p_variance_percent, p_severity,
        p_possible_reason, 'OPEN', p_owner_id, p_sla_deadline,
        0, NOW(), NOW()
    );

    SELECT 
        ec.id, ec.financial_record_id, ec.variance_percent, ec.severity,
        ec.possible_reason, ec.status, ec.owner_id, ec.sla_deadline,
        ec.escalation_level, ec.created_at, ec.updated_at,
        fr.category AS record_category, fr.period AS record_period,
        fr.department AS record_department, fr.budget_amount AS record_budget,
        fr.actual_amount AS record_actual, fr.created_at AS record_created_at,
        o.name AS owner_name, o.email AS owner_email, o.role AS owner_role, o.level AS owner_level
    FROM exception_cases ec
    LEFT JOIN financial_records fr ON ec.financial_record_id = fr.id
    LEFT JOIN owners o ON ec.owner_id = o.id
    WHERE ec.id = LAST_INSERT_ID();
END$$

-- 5. Get Exceptions (Filtered or All)
DROP PROCEDURE IF EXISTS sp_get_exceptions$$
CREATE PROCEDURE sp_get_exceptions(
    IN p_severity VARCHAR(20),
    IN p_status VARCHAR(20)
)
BEGIN
    SELECT 
        ec.id, ec.financial_record_id, ec.variance_percent, ec.severity,
        ec.possible_reason, ec.status, ec.owner_id, ec.sla_deadline,
        ec.escalation_level, ec.created_at, ec.updated_at,
        fr.category AS record_category, fr.period AS record_period,
        fr.department AS record_department, fr.budget_amount AS record_budget,
        fr.actual_amount AS record_actual, fr.created_at AS record_created_at,
        o.name AS owner_name, o.email AS owner_email, o.role AS owner_role, o.level AS owner_level
    FROM exception_cases ec
    LEFT JOIN financial_records fr ON ec.financial_record_id = fr.id
    LEFT JOIN owners o ON ec.owner_id = o.id
    WHERE (p_severity IS NULL OR p_severity = '' OR ec.severity = p_severity)
      AND (p_status IS NULL OR p_status = '' OR ec.status = p_status)
    ORDER BY ec.id DESC;
END$$

-- 6. Get Exception By ID
DROP PROCEDURE IF EXISTS sp_get_exception_by_id$$
CREATE PROCEDURE sp_get_exception_by_id(
    IN p_exception_id INT
)
BEGIN
    SELECT 
        ec.id, ec.financial_record_id, ec.variance_percent, ec.severity,
        ec.possible_reason, ec.status, ec.owner_id, ec.sla_deadline,
        ec.escalation_level, ec.created_at, ec.updated_at,
        fr.category AS record_category, fr.period AS record_period,
        fr.department AS record_department, fr.budget_amount AS record_budget,
        fr.actual_amount AS record_actual, fr.created_at AS record_created_at,
        o.name AS owner_name, o.email AS owner_email, o.role AS owner_role, o.level AS owner_level
    FROM exception_cases ec
    LEFT JOIN financial_records fr ON ec.financial_record_id = fr.id
    LEFT JOIN owners o ON ec.owner_id = o.id
    WHERE ec.id = p_exception_id;
END$$

-- 7. Get Overdue Exceptions
DROP PROCEDURE IF EXISTS sp_get_overdue_exceptions$$
CREATE PROCEDURE sp_get_overdue_exceptions()
BEGIN
    SELECT 
        ec.id, ec.financial_record_id, ec.variance_percent, ec.severity,
        ec.possible_reason, ec.status, ec.owner_id, ec.sla_deadline,
        ec.escalation_level, ec.created_at, ec.updated_at,
        fr.category AS record_category, fr.period AS record_period,
        fr.department AS record_department, fr.budget_amount AS record_budget,
        fr.actual_amount AS record_actual, fr.created_at AS record_created_at,
        o.name AS owner_name, o.email AS owner_email, o.role AS owner_role, o.level AS owner_level
    FROM exception_cases ec
    LEFT JOIN financial_records fr ON ec.financial_record_id = fr.id
    LEFT JOIN owners o ON ec.owner_id = o.id
    WHERE ec.sla_deadline < NOW() AND ec.status != 'RESOLVED'
    ORDER BY ec.sla_deadline ASC;
END$$

-- 8. Update Exception
DROP PROCEDURE IF EXISTS sp_update_exception$$
CREATE PROCEDURE sp_update_exception(
    IN p_exception_id INT,
    IN p_status VARCHAR(20),
    IN p_owner_id INT,
    IN p_possible_reason TEXT
)
BEGIN
    UPDATE exception_cases
    SET 
        status = IF(p_status IS NOT NULL AND p_status != '', p_status, status),
        owner_id = IF(p_owner_id IS NOT NULL AND p_owner_id > 0, p_owner_id, owner_id),
        possible_reason = IF(p_possible_reason IS NOT NULL AND p_possible_reason != '', p_possible_reason, possible_reason),
        updated_at = NOW()
    WHERE id = p_exception_id;

    CALL sp_get_exception_by_id(p_exception_id);
END$$

-- 9. Escalate Exception
DROP PROCEDURE IF EXISTS sp_escalate_exception$$
CREATE PROCEDURE sp_escalate_exception(
    IN p_exception_id INT
)
BEGIN
    DECLARE v_current_owner_id INT;
    DECLARE v_current_level INT DEFAULT 1;
    DECLARE v_next_owner_id INT;

    SELECT owner_id INTO v_current_owner_id
    FROM exception_cases
    WHERE id = p_exception_id;

    IF v_current_owner_id IS NOT NULL THEN
        SELECT level INTO v_current_level
        FROM owners
        WHERE id = v_current_owner_id;
    END IF;

    -- Find next owner with higher level
    SELECT id INTO v_next_owner_id
    FROM owners
    WHERE level > v_current_level
    ORDER BY level ASC
    LIMIT 1;

    -- If no higher level, keep highest level owner
    IF v_next_owner_id IS NULL THEN
        SELECT id INTO v_next_owner_id
        FROM owners
        ORDER BY level DESC
        LIMIT 1;
    END IF;

    UPDATE exception_cases
    SET 
        owner_id = IFNULL(v_next_owner_id, owner_id),
        escalation_level = escalation_level + 1,
        status = 'ESCALATED',
        updated_at = NOW()
    WHERE id = p_exception_id;

    CALL sp_get_exception_by_id(p_exception_id);
END$$

-- 10. Dashboard Summary
DROP PROCEDURE IF EXISTS sp_get_dashboard_summary$$
CREATE PROCEDURE sp_get_dashboard_summary()
BEGIN
    SELECT
        (SELECT COUNT(*) FROM financial_records) AS total_financial_records,
        (SELECT COUNT(*) FROM exception_cases) AS total_exceptions,
        (SELECT COUNT(*) FROM exception_cases WHERE severity = 'LOW') AS count_low,
        (SELECT COUNT(*) FROM exception_cases WHERE severity = 'MEDIUM') AS count_medium,
        (SELECT COUNT(*) FROM exception_cases WHERE severity = 'HIGH') AS count_high,
        (SELECT COUNT(*) FROM exception_cases WHERE severity = 'CRITICAL') AS count_critical,
        (SELECT COUNT(*) FROM exception_cases WHERE status = 'OPEN') AS count_open,
        (SELECT COUNT(*) FROM exception_cases WHERE status = 'IN_PROGRESS') AS count_in_progress,
        (SELECT COUNT(*) FROM exception_cases WHERE status = 'RESOLVED') AS count_resolved,
        (SELECT COUNT(*) FROM exception_cases WHERE status = 'ESCALATED') AS count_escalated,
        (SELECT COUNT(*) FROM exception_cases WHERE sla_deadline < NOW() AND status != 'RESOLVED') AS overdue_exceptions;
END$$

DELIMITER ;

