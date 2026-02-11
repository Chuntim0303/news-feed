-- Migration: Create companies and company_aliases tables
-- Database: MySQL
-- Description: Creates reference tables for stock ticker data, replacing hardcoded stock_ticker_data.py

-- Create companies table
CREATE TABLE IF NOT EXISTS companies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'Primary company name used for matching (lowercase)',
    ticker VARCHAR(20) NOT NULL COMMENT 'Stock ticker symbol (e.g., GOOGL)',
    exchange VARCHAR(50) COMMENT 'Stock exchange (e.g., NASDAQ, NYSE)',
    full_name VARCHAR(255) COMMENT 'Full legal company name',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_name (name),
    UNIQUE KEY unique_ticker_exchange (ticker, exchange),
    INDEX idx_ticker (ticker),
    INDEX idx_name (name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create company_aliases table
CREATE TABLE IF NOT EXISTS company_aliases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT NOT NULL,
    alias VARCHAR(255) NOT NULL COMMENT 'Alternative name for the company (lowercase)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    UNIQUE KEY unique_alias (alias),
    INDEX idx_company_id (company_id),
    INDEX idx_alias (alias)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
