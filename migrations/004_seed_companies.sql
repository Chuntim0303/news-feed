-- Seed: Populate companies table with initial data from stock_ticker_data.py
-- Database: MySQL
-- Run AFTER 004_create_companies_table.sql

-- Pharmaceutical Companies
INSERT INTO companies (name, ticker, exchange, full_name) VALUES
('astellas', '4503.T', 'Tokyo Stock Exchange', 'Astellas Pharma Inc.'),
('pfizer', 'PFE', 'NYSE', 'Pfizer Inc.'),
('novartis', 'NVS', 'NYSE', 'Novartis AG'),
('roche', 'RHHBY', 'OTC', 'Roche Holding AG'),
('merck', 'MRK', 'NYSE', 'Merck & Co., Inc.'),
('johnson & johnson', 'JNJ', 'NYSE', 'Johnson & Johnson'),
('bristol myers squibb', 'BMY', 'NYSE', 'Bristol Myers Squibb Company'),
('eli lilly', 'LLY', 'NYSE', 'Eli Lilly and Company'),
('abbvie', 'ABBV', 'NYSE', 'AbbVie Inc.'),
('amgen', 'AMGN', 'NASDAQ', 'Amgen Inc.'),
('gilead', 'GILD', 'NASDAQ', 'Gilead Sciences, Inc.'),
('gsk', 'GSK', 'NYSE', 'GSK plc'),
('sanofi', 'SNY', 'NASDAQ', 'Sanofi S.A.'),
('astrazeneca', 'AZN', 'NASDAQ', 'AstraZeneca PLC'),
('novo nordisk', 'NVO', 'NYSE', 'Novo Nordisk A/S'),
('bayer', 'BAYRY', 'OTC', 'Bayer AG'),
('takeda', 'TAK', 'NYSE', 'Takeda Pharmaceutical Company Limited'),
-- Biotech Companies
('moderna', 'MRNA', 'NASDAQ', 'Moderna, Inc.'),
('biontech', 'BNTX', 'NASDAQ', 'BioNTech SE'),
('vertex', 'VRTX', 'NASDAQ', 'Vertex Pharmaceuticals Incorporated'),
('regeneron', 'REGN', 'NASDAQ', 'Regeneron Pharmaceuticals, Inc.'),
('biogen', 'BIIB', 'NASDAQ', 'Biogen Inc.'),
('illumina', 'ILMN', 'NASDAQ', 'Illumina, Inc.'),
('genentech', 'RHHBY', 'OTC', 'Genentech, Inc. (Roche subsidiary)'),
-- Medical Device / Healthcare
('medtronic', 'MDT', 'NYSE', 'Medtronic plc'),
('abbott', 'ABT', 'NYSE', 'Abbott Laboratories'),
('ge healthcare', 'GEHC', 'NASDAQ', 'GE HealthCare Technologies Inc.'),
-- Major Tech Companies
('alphabet', 'GOOGL', 'NASDAQ', 'Alphabet Inc.'),
('apple', 'AAPL', 'NASDAQ', 'Apple Inc.'),
('microsoft', 'MSFT', 'NASDAQ', 'Microsoft Corporation'),
('amazon', 'AMZN', 'NASDAQ', 'Amazon.com, Inc.'),
('meta', 'META', 'NASDAQ', 'Meta Platforms, Inc.'),
('nvidia', 'NVDA', 'NASDAQ', 'NVIDIA Corporation'),
('tesla', 'TSLA', 'NASDAQ', 'Tesla, Inc.'),
('netflix', 'NFLX', 'NASDAQ', 'Netflix, Inc.'),
('intel', 'INTC', 'NASDAQ', 'Intel Corporation'),
('amd', 'AMD', 'NASDAQ', 'Advanced Micro Devices, Inc.'),
('broadcom', 'AVGO', 'NASDAQ', 'Broadcom Inc.'),
('salesforce', 'CRM', 'NYSE', 'Salesforce, Inc.'),
('oracle', 'ORCL', 'NYSE', 'Oracle Corporation'),
('ibm', 'IBM', 'NYSE', 'International Business Machines Corporation'),
('qualcomm', 'QCOM', 'NASDAQ', 'QUALCOMM Incorporated'),
-- Other Companies
('palantir', 'PLTR', 'NYSE', 'Palantir Technologies Inc.'),
('kkr', 'KKR', 'NYSE', 'KKR & Co. Inc.'),
('gemini', 'GEMI', 'NASDAQ', 'Gemini Space Station Inc.'),
('hims', 'HIMS', 'NYSE', 'Hims & Hers Health Inc.'),
('barrick', 'GOLD', 'NYSE', 'Barrick Gold Corporation'),
('agco', 'AGCO', 'NYSE', 'AGCO Corporation'),
('ares', 'ARES', 'NYSE', 'Ares Management Corporation'),
('metlife', 'MET', 'NYSE', 'MetLife, Inc.'),
('robinhood', 'HOOD', 'NASDAQ', 'Robinhood Markets, Inc.')
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name);

-- Aliases
INSERT INTO company_aliases (company_id, alias)
SELECT c.id, a.alias FROM companies c
JOIN (
    SELECT 'astellas' AS name, 'astellas pharma' AS alias
    UNION ALL SELECT 'roche', 'roche holding'
    UNION ALL SELECT 'merck', 'merck & co'
    UNION ALL SELECT 'johnson & johnson', 'j&j'
    UNION ALL SELECT 'johnson & johnson', 'jnj'
    UNION ALL SELECT 'bristol myers squibb', 'bms'
    UNION ALL SELECT 'bristol myers squibb', 'bristol-myers'
    UNION ALL SELECT 'eli lilly', 'lilly'
    UNION ALL SELECT 'gilead', 'gilead sciences'
    UNION ALL SELECT 'gsk', 'glaxosmithkline'
    UNION ALL SELECT 'novo nordisk', 'novo'
    UNION ALL SELECT 'takeda', 'takeda pharmaceutical'
    UNION ALL SELECT 'vertex', 'vertex pharmaceuticals'
    UNION ALL SELECT 'ge healthcare', 'ge health'
    UNION ALL SELECT 'alphabet', 'google'
    UNION ALL SELECT 'meta', 'facebook'
    UNION ALL SELECT 'nvidia', 'nvda'
    UNION ALL SELECT 'amd', 'advanced micro devices'
    UNION ALL SELECT 'hims', 'hims & hers'
    UNION ALL SELECT 'barrick', 'barrick gold'
    UNION ALL SELECT 'ares', 'ares management'
) a ON c.name = a.name
ON DUPLICATE KEY UPDATE alias = VALUES(alias);
