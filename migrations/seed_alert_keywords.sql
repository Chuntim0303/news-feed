-- Seed alert_keywords table with common biotech/pharma keywords
-- These keywords will trigger alerts when found in article titles/summaries
-- Used by: aws-lambda/services/keyword_alert_service.py

-- Clear existing keywords (optional - comment out if you want to keep existing)
-- TRUNCATE TABLE alert_keywords;

-- Insert high-impact keywords (event_score 8-10)
INSERT INTO alert_keywords (keyword, event_score, is_active) VALUES
-- FDA & Regulatory
('FDA approval', 10, 1),
('FDA approves', 10, 1),
('FDA rejects', 10, 1),
('FDA rejection', 10, 1),
('breakthrough therapy', 9, 1),
('fast track', 8, 1),
('orphan drug', 8, 1),
('priority review', 9, 1),
('PDUFA date', 9, 1),
('complete response letter', 10, 1),
('CRL', 10, 1),

-- Clinical Trials
('phase 3 results', 9, 1),
('phase 3 trial', 8, 1),
('trial success', 9, 1),
('trial failure', 9, 1),
('trial halted', 10, 1),
('trial stopped', 10, 1),
('meets primary endpoint', 9, 1),
('misses endpoint', 9, 1),
('statistically significant', 8, 1),

-- M&A and Deals
('acquisition', 9, 1),
('merger', 9, 1),
('buyout', 10, 1),
('takeover', 9, 1),
('licensing deal', 8, 1),
('collaboration', 7, 1),
('partnership', 7, 1);

-- Insert medium-impact keywords (event_score 5-7)
INSERT INTO alert_keywords (keyword, event_score, is_active) VALUES
-- Clinical Development
('phase 2 results', 7, 1),
('phase 1 results', 6, 1),
('clinical data', 6, 1),
('interim analysis', 7, 1),
('enrollment complete', 6, 1),
('dosing', 5, 1),

-- Financial
('earnings beat', 7, 1),
('earnings miss', 7, 1),
('guidance raised', 7, 1),
('guidance lowered', 7, 1),
('revenue growth', 6, 1),
('profit', 5, 1),

-- Product & Commercial
('launch', 6, 1),
('commercial', 6, 1),
('sales growth', 6, 1),
('market share', 5, 1),
('reimbursement', 6, 1);

-- Insert lower-impact keywords (event_score 3-4)
INSERT INTO alert_keywords (keyword, event_score, is_active) VALUES
-- General Development
('pipeline', 4, 1),
('development', 3, 1),
('research', 3, 1),
('preclinical', 4, 1),
('discovery', 3, 1),

-- Corporate
('CEO', 4, 1),
('management', 3, 1),
('executive', 3, 1),
('board', 3, 1),

-- Financing
('offering', 4, 1),
('financing', 4, 1),
('capital raise', 4, 1),
('IPO', 5, 1);

-- Verify insertion
SELECT 
    COUNT(*) as total_keywords,
    MIN(event_score) as min_score,
    MAX(event_score) as max_score,
    AVG(event_score) as avg_score
FROM alert_keywords
WHERE is_active = 1;

-- Show sample keywords by score
SELECT 
    event_score,
    COUNT(*) as count,
    GROUP_CONCAT(keyword SEPARATOR ', ') as keywords
FROM alert_keywords
WHERE is_active = 1
GROUP BY event_score
ORDER BY event_score DESC;
