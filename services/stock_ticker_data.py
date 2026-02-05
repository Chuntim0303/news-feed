"""
Stock Ticker Mapping Data

This file contains mappings of company names to their stock ticker symbols.
Focused on pharmaceutical, biotech, and healthcare companies commonly mentioned
in Bloomberg and Fierce Biotech feeds.

Data structure:
- Keys: Company names (lowercase for case-insensitive matching)
- Values: Dict with ticker, exchange, and full company name
"""

COMPANY_TICKER_MAP = {
    # Pharmaceutical Companies
    "astellas": {
        "ticker": "4503.T",
        "exchange": "Tokyo Stock Exchange",
        "full_name": "Astellas Pharma Inc.",
        "aliases": ["astellas pharma"]
    },
    "pfizer": {
        "ticker": "PFE",
        "exchange": "NYSE",
        "full_name": "Pfizer Inc.",
        "aliases": []
    },
    "novartis": {
        "ticker": "NVS",
        "exchange": "NYSE",
        "full_name": "Novartis AG",
        "aliases": []
    },
    "roche": {
        "ticker": "RHHBY",
        "exchange": "OTC",
        "full_name": "Roche Holding AG",
        "aliases": ["roche holding"]
    },
    "merck": {
        "ticker": "MRK",
        "exchange": "NYSE",
        "full_name": "Merck & Co., Inc.",
        "aliases": ["merck & co"]
    },
    "johnson & johnson": {
        "ticker": "JNJ",
        "exchange": "NYSE",
        "full_name": "Johnson & Johnson",
        "aliases": ["j&j", "jnj"]
    },
    "bristol myers squibb": {
        "ticker": "BMY",
        "exchange": "NYSE",
        "full_name": "Bristol Myers Squibb Company",
        "aliases": ["bms", "bristol-myers"]
    },
    "eli lilly": {
        "ticker": "LLY",
        "exchange": "NYSE",
        "full_name": "Eli Lilly and Company",
        "aliases": ["lilly"]
    },
    "abbvie": {
        "ticker": "ABBV",
        "exchange": "NYSE",
        "full_name": "AbbVie Inc.",
        "aliases": []
    },
    "amgen": {
        "ticker": "AMGN",
        "exchange": "NASDAQ",
        "full_name": "Amgen Inc.",
        "aliases": []
    },
    "gilead": {
        "ticker": "GILD",
        "exchange": "NASDAQ",
        "full_name": "Gilead Sciences, Inc.",
        "aliases": ["gilead sciences"]
    },
    "gsk": {
        "ticker": "GSK",
        "exchange": "NYSE",
        "full_name": "GSK plc",
        "aliases": ["glaxosmithkline"]
    },
    "sanofi": {
        "ticker": "SNY",
        "exchange": "NASDAQ",
        "full_name": "Sanofi S.A.",
        "aliases": []
    },
    "astrazeneca": {
        "ticker": "AZN",
        "exchange": "NASDAQ",
        "full_name": "AstraZeneca PLC",
        "aliases": []
    },
    "novo nordisk": {
        "ticker": "NVO",
        "exchange": "NYSE",
        "full_name": "Novo Nordisk A/S",
        "aliases": ["novo"]
    },
    "bayer": {
        "ticker": "BAYRY",
        "exchange": "OTC",
        "full_name": "Bayer AG",
        "aliases": []
    },
    "takeda": {
        "ticker": "TAK",
        "exchange": "NYSE",
        "full_name": "Takeda Pharmaceutical Company Limited",
        "aliases": ["takeda pharmaceutical"]
    },

    # Biotech Companies
    "moderna": {
        "ticker": "MRNA",
        "exchange": "NASDAQ",
        "full_name": "Moderna, Inc.",
        "aliases": []
    },
    "biontech": {
        "ticker": "BNTX",
        "exchange": "NASDAQ",
        "full_name": "BioNTech SE",
        "aliases": []
    },
    "vertex": {
        "ticker": "VRTX",
        "exchange": "NASDAQ",
        "full_name": "Vertex Pharmaceuticals Incorporated",
        "aliases": ["vertex pharmaceuticals"]
    },
    "regeneron": {
        "ticker": "REGN",
        "exchange": "NASDAQ",
        "full_name": "Regeneron Pharmaceuticals, Inc.",
        "aliases": []
    },
    "biogen": {
        "ticker": "BIIB",
        "exchange": "NASDAQ",
        "full_name": "Biogen Inc.",
        "aliases": []
    },
    "illumina": {
        "ticker": "ILMN",
        "exchange": "NASDAQ",
        "full_name": "Illumina, Inc.",
        "aliases": []
    },
    "genentech": {
        "ticker": "RHHBY",
        "exchange": "OTC",
        "full_name": "Genentech, Inc. (Roche subsidiary)",
        "aliases": []
    },

    # Medical Device / Healthcare
    "medtronic": {
        "ticker": "MDT",
        "exchange": "NYSE",
        "full_name": "Medtronic plc",
        "aliases": []
    },
    "abbott": {
        "ticker": "ABT",
        "exchange": "NYSE",
        "full_name": "Abbott Laboratories",
        "aliases": []
    },
    "ge healthcare": {
        "ticker": "GEHC",
        "exchange": "NASDAQ",
        "full_name": "GE HealthCare Technologies Inc.",
        "aliases": []
    },

    # Other Companies (from Bloomberg)
    "palantir": {
        "ticker": "PLTR",
        "exchange": "NYSE",
        "full_name": "Palantir Technologies Inc.",
        "aliases": []
    },
    "kkr": {
        "ticker": "KKR",
        "exchange": "NYSE",
        "full_name": "KKR & Co. Inc.",
        "aliases": []
    },
    "gemini": {
        "ticker": "GEMI",
        "exchange": "NASDAQ",
        "full_name": "Gemini Space Station Inc.",
        "aliases": []
    },
    "hims": {
        "ticker": "HIMS",
        "exchange": "NYSE",
        "full_name": "Hims & Hers Health Inc.",
        "aliases": ["hims & hers"]
    },
    "barrick": {
        "ticker": "GOLD",
        "exchange": "NYSE",
        "full_name": "Barrick Gold Corporation",
        "aliases": ["barrick gold"]
    },
    "agco": {
        "ticker": "AGCO",
        "exchange": "NYSE",
        "full_name": "AGCO Corporation",
        "aliases": []
    },
    "ares": {
        "ticker": "ARES",
        "exchange": "NYSE",
        "full_name": "Ares Management Corporation",
        "aliases": ["ares management"]
    },
    "metlife": {
        "ticker": "MET",
        "exchange": "NYSE",
        "full_name": "MetLife, Inc.",
        "aliases": []
    },
    "robinhood": {
        "ticker": "HOOD",
        "exchange": "NASDAQ",
        "full_name": "Robinhood Markets, Inc.",
        "aliases": []
    }
}

# Build reverse index for aliases
ALIAS_TO_COMPANY = {}
for company, data in COMPANY_TICKER_MAP.items():
    # Add the main company name
    ALIAS_TO_COMPANY[company] = company
    # Add all aliases
    for alias in data.get("aliases", []):
        ALIAS_TO_COMPANY[alias.lower()] = company
