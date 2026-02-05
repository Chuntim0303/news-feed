-- Migration: Create RSS tracking system tables
-- Database: MySQL
-- Description: Creates rss_feeds and rss_items tables for tracking RSS feed data

-- Create rss_feeds table
CREATE TABLE IF NOT EXISTS rss_feeds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url VARCHAR(500) NOT NULL UNIQUE,
    title VARCHAR(255),
    site_url VARCHAR(500),
    description TEXT,
    language VARCHAR(50),
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    last_fetch_at DATETIME,
    next_fetch_at DATETIME,
    fetch_interval_minutes INT DEFAULT 60,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_url (url),
    INDEX idx_next_fetch (next_fetch_at, is_active),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create rss_items table
CREATE TABLE IF NOT EXISTS rss_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feed_id INT NOT NULL,
    guid VARCHAR(500) NOT NULL,
    link VARCHAR(1000),
    title VARCHAR(500),
    author VARCHAR(255),
    summary TEXT,
    content LONGTEXT,
    image_url VARCHAR(1000),
    published_at DATETIME,
    fetched_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (feed_id) REFERENCES rss_feeds(id) ON DELETE CASCADE,
    UNIQUE KEY unique_feed_guid (feed_id, guid),
    INDEX idx_feed_id (feed_id),
    INDEX idx_published_at (published_at),
    INDEX idx_fetched_at (fetched_at),
    INDEX idx_guid (guid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
