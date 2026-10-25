"""Reference data for Maharashtra: districts, aliases, categories, search keywords.

Only districts are seeded. Talukas and locations are added progressively
(auto-created from imports, or bulk-loaded with POST /import/geo).
"""

# The 36 districts of Maharashtra, using current official names.
DISTRICTS = [
    "Ahilyanagar", "Akola", "Amravati", "Beed", "Bhandara", "Buldhana",
    "Chandrapur", "Chhatrapati Sambhajinagar", "Dharashiv", "Dhule",
    "Gadchiroli", "Gondia", "Hingoli", "Jalgaon", "Jalna", "Kolhapur",
    "Latur", "Mumbai City", "Mumbai Suburban", "Nagpur", "Nanded",
    "Nandurbar", "Nashik", "Palghar", "Parbhani", "Pune", "Raigad",
    "Ratnagiri", "Sangli", "Satara", "Sindhudurg", "Solapur", "Thane",
    "Wardha", "Washim", "Yavatmal",
]

# Old names / common spellings -> official district name (keys are lowercase).
# "Mumbai" alone is deliberately NOT mapped: it could be either Mumbai district.
DISTRICT_ALIASES = {
    "ahmednagar": "Ahilyanagar", "ahmadnagar": "Ahilyanagar", "ahilya nagar": "Ahilyanagar",
    "aurangabad": "Chhatrapati Sambhajinagar", "sambhajinagar": "Chhatrapati Sambhajinagar",
    "chh. sambhajinagar": "Chhatrapati Sambhajinagar", "ch sambhajinagar": "Chhatrapati Sambhajinagar",
    "osmanabad": "Dharashiv",
    "bid": "Beed",
    "buldana": "Buldhana",
    "gondiya": "Gondia",
    "raigarh": "Raigad",
    "poona": "Pune",
    "nasik": "Nashik",
    "sholapur": "Solapur",
    "mumbai suburb": "Mumbai Suburban",
    "bombay city": "Mumbai City",
    "yeotmal": "Yavatmal",
    "jalana": "Jalna",
}

CATEGORIES = [
    "Xerox", "Photocopy", "Printing", "Digital Printing", "Stationery",
    "Cyber Cafe", "CSC", "DTP", "Online Services", "E-Seva",
    "Computer Shop", "Xerox + Printing", "Other",
]

# Ordered (pattern, category) rules used to standardise free-text categories
# and to classify a shop from its name. Patterns match on normalised lowercase text.
CATEGORY_RULES = [
    (r"\bxerox\b.*\bprint|\bprint.*\bxerox\b", "Xerox + Printing"),
    (r"\b(xerox|zerox|xerx|zeorx)\b", "Xerox"),
    (r"\b(photo ?copy|photostat|copy cent(er|re)|copier)\b", "Photocopy"),
    (r"\bdigital print", "Digital Printing"),
    (r"\b(print|printing|printers?|press|offset|flex)\b", "Printing"),
    (r"\b(stationery|stationary|stationers?)\b", "Stationery"),
    (r"\b(cyber|internet cafe|net cafe)\b", "Cyber Cafe"),
    (r"\b(csc|common service cent(er|re)|aaple sarkar|aapale sarkar|apale sarkar)\b", "CSC"),
    (r"\b(dtp|desk ?top publishing)\b", "DTP"),
    (r"\b(e ?seva|e ?sewa|maha ?e ?seva|setu)\b", "E-Seva"),
    (r"\b(online (services?|forms?)|online form|online cent(er|re)|document cent(er|re)|form cent(er|re))\b", "Online Services"),
    (r"\b(computers?|laptop)\b", "Computer Shop"),
]

SEARCH_KEYWORDS = [
    "Xerox", "Xerox shop", "Xerox centre", "Xerox center", "photocopy",
    "photocopy shop", "copy centre", "printing shop", "digital printing",
    "stationery xerox", "cyber cafe", "CSC", "DTP centre", "online services",
    "e seva", "computer xerox", "printing and xerox", "online form center",
    "document center",
]

LEAD_STATUSES = [
    "New", "Not Contacted", "Contacted", "Interested", "Follow Up",
    "Not Interested", "Converted", "Invalid", "Do Not Contact",
]

VERIFICATION_STATUSES = ["unverified", "verified", "invalid"]
DUPLICATE_STATUSES = ["unique", "possible_duplicate", "confirmed_duplicate"]

OFFICE_TYPES = [
    "Talathi Office", "Tehsil Office", "Tahsildar Office", "Setu Office",
    "Sub-Registrar Office", "District Collector Office", "Other Government Office",
]

# Maharashtra PIN codes start with 40-44.
MAHARASHTRA_PIN_PREFIXES = ("40", "41", "42", "43", "44")

TEST_DATA_SOURCE = "TEST_DATA"
