-- ============================================================
-- FEMA Stored Procedures
-- Split each executable block with: -- PROCEDURE_DELIMITER
-- ============================================================

USE fema_db;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_add_financial_record;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_all_financial_records;

-- PROCEDURE_DELIMITER
CREATE PROCEDURE sp_get_all_financial_records()
BEGIN
    SELECT id, category, period, department, budget_amount, actual_amount, created_at
    FROM financial_records
    ORDER BY id DESC;
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_unprocessed_financial_records;

-- PROCEDURE_DELIMITER
CREATE PROCEDURE sp_get_unprocessed_financial_records()
BEGIN
    SELECT fr.id, fr.category, fr.period, fr.department, fr.budget_amount, fr.actual_amount, fr.created_at
    FROM financial_records fr
    LEFT JOIN exception_cases ec ON fr.id = ec.financial_record_id
    WHERE ec.id IS NULL
    ORDER BY fr.id ASC;
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_create_exception_case;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_exceptions;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_exception_by_id;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_overdue_exceptions;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_update_exception;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_escalate_exception;

-- PROCEDURE_DELIMITER
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
END;

-- PROCEDURE_DELIMITER
DROP PROCEDURE IF EXISTS sp_get_dashboard_summary;

-- PROCEDURE_DELIMITER
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
END;
