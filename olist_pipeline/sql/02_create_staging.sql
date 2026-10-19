CREATE DATABASE IF NOT EXISTS olist_staging
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE olist_staging;

CREATE TABLE IF NOT EXISTS etl_batch (
  batch_id CHAR(36) PRIMARY KEY,
  pipeline_name VARCHAR(100) NOT NULL,
  load_mode ENUM('full','incremental') NOT NULL,
  business_date DATE NOT NULL,
  started_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6),
  watermark_start DATETIME(6),
  watermark_end DATETIME(6) NOT NULL,
  status ENUM('RUNNING','SUCCESS','FAILED') NOT NULL,
  source_rows BIGINT DEFAULT 0,
  clean_rows BIGINT DEFAULT 0,
  rejected_rows BIGINT DEFAULT 0,
  message TEXT,
  INDEX idx_batch_status (status, started_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_watermark (
  pipeline_name VARCHAR(100) NOT NULL,
  source_table VARCHAR(100) NOT NULL,
  last_successful_watermark DATETIME(6),
  last_batch_id CHAR(36),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (pipeline_name, source_table)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS etl_reject (
  reject_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  source_table VARCHAR(128) NOT NULL,
  business_key VARCHAR(255),
  rule_id VARCHAR(128),
  dimension_name VARCHAR(128),
  severity VARCHAR(16),
  column_name VARCHAR(128),
  original_value TEXT,
  rejection_reason TEXT,
  raw_record JSON,
  rejected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_reject_batch (batch_id),
  INDEX idx_reject_rule (rule_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dq_rule_result (
  result_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  rule_id VARCHAR(128) NOT NULL,
  dimension_name VARCHAR(128),
  severity VARCHAR(16),
  description TEXT,
  detected_count BIGINT DEFAULT 0,
  corrected_count BIGINT DEFAULT 0,
  quarantined_count BIGINT DEFAULT 0,
  open_count BIGINT DEFAULT 0,
  result VARCHAR(32),
  INDEX idx_dq_result_batch (batch_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dq_issue_detail (
  issue_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  source_table VARCHAR(128) NOT NULL,
  record_key VARCHAR(255),
  rule_id VARCHAR(128),
  dimension_name VARCHAR(128),
  severity VARCHAR(16),
  column_name VARCHAR(128),
  original_value TEXT,
  action_taken TEXT,
  disposition VARCHAR(32),
  detail TEXT,
  INDEX idx_issue_batch (batch_id),
  INDEX idx_issue_rule (rule_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dq_transformation_log (
  transformation_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  source_table VARCHAR(128),
  action_name VARCHAR(255),
  affected_rows BIGINT,
  detail TEXT,
  INDEX idx_transform_batch (batch_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dq_table_profile (
  profile_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  table_name VARCHAR(128),
  raw_rows BIGINT,
  clean_rows BIGINT,
  valid_rows BIGINT,
  corrected_rows BIGINT,
  warning_rows BIGINT,
  error_rows BIGINT,
  raw_exact_duplicate_rows BIGINT,
  clean_exact_duplicate_rows BIGINT,
  INDEX idx_profile_batch (batch_id)
) ENGINE=InnoDB;
