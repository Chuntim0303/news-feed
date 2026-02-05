-- Rollback Migration: Drop RSS tracking system tables
-- Database: MySQL
-- Description: Drops rss_items and rss_feeds tables

-- Drop rss_items table first (due to foreign key constraint)
DROP TABLE IF EXISTS rss_items;

-- Drop rss_feeds table
DROP TABLE IF EXISTS rss_feeds;
