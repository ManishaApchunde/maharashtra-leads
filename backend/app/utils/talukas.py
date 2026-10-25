"""All talukas of Maharashtra, by district (official district names as in DISTRICTS).

Used by the "whole district" collector to loop every taluka automatically, and seeded
into the talukas table on startup so the Taluka dropdowns are filled.

Mumbai City has no talukas, so it is covered by CITY_AREAS only.
Villages are NOT bundled (Maharashtra has ~43,000). The collector searches every
village/town already in the database (imported via POST /import/geo, or discovered from
earlier search results) and can optionally sweep the district on a map grid.
"""

MAHARASHTRA_TALUKAS: dict[str, list[str]] = {
    "Ahilyanagar": ["Ahilyanagar", "Akole", "Jamkhed", "Karjat", "Kopargaon", "Nevasa", "Parner", "Pathardi",
                    "Rahata", "Rahuri", "Sangamner", "Shevgaon", "Shrigonda", "Shrirampur"],
    "Akola": ["Akola", "Akot", "Balapur", "Barshitakli", "Murtizapur", "Patur", "Telhara"],
    "Amravati": ["Achalpur", "Amravati", "Anjangaon Surji", "Bhatkuli", "Chandur Bazar", "Chandur Railway",
                 "Chikhaldara", "Daryapur", "Dhamangaon Railway", "Dharni", "Morshi", "Nandgaon Khandeshwar",
                 "Teosa", "Warud"],
    "Beed": ["Ambajogai", "Ashti", "Beed", "Dharur", "Georai", "Kaij", "Majalgaon", "Parli", "Patoda",
             "Shirur Kasar", "Wadwani"],
    "Bhandara": ["Bhandara", "Lakhandur", "Lakhani", "Mohadi", "Pauni", "Sakoli", "Tumsar"],
    "Buldhana": ["Buldhana", "Chikhli", "Deulgaon Raja", "Jalgaon Jamod", "Khamgaon", "Lonar", "Malkapur",
                 "Mehkar", "Motala", "Nandura", "Sangrampur", "Shegaon", "Sindkhed Raja"],
    "Chandrapur": ["Ballarpur", "Bhadravati", "Brahmapuri", "Chandrapur", "Chimur", "Gondpipri", "Jiwati",
                   "Korpana", "Mul", "Nagbhid", "Pombhurna", "Rajura", "Sawali", "Sindewahi", "Warora"],
    "Chhatrapati Sambhajinagar": ["Chhatrapati Sambhajinagar", "Gangapur", "Kannad", "Khuldabad", "Paithan",
                                  "Phulambri", "Sillod", "Soegaon", "Vaijapur"],
    "Dharashiv": ["Bhum", "Dharashiv", "Kalamb", "Lohara", "Paranda", "Tuljapur", "Umarga", "Washi"],
    "Dhule": ["Dhule", "Sakri", "Shindkheda", "Shirpur"],
    "Gadchiroli": ["Aheri", "Armori", "Bhamragad", "Chamorshi", "Desaiganj", "Dhanora", "Etapalli",
                   "Gadchiroli", "Korchi", "Kurkheda", "Mulchera", "Sironcha"],
    "Gondia": ["Amgaon", "Arjuni Morgaon", "Deori", "Gondia", "Goregaon", "Sadak Arjuni", "Salekasa", "Tirora"],
    "Hingoli": ["Aundha Nagnath", "Basmat", "Hingoli", "Kalamnuri", "Sengaon"],
    "Jalgaon": ["Amalner", "Bhadgaon", "Bhusawal", "Bodwad", "Chalisgaon", "Chopda", "Dharangaon", "Erandol",
                "Jalgaon", "Jamner", "Muktainagar", "Pachora", "Parola", "Raver", "Yawal"],
    "Jalna": ["Ambad", "Badnapur", "Bhokardan", "Ghansawangi", "Jafrabad", "Jalna", "Mantha", "Partur"],
    "Kolhapur": ["Ajra", "Bhudargad", "Chandgad", "Gadhinglaj", "Gaganbawada", "Hatkanangle", "Kagal",
                 "Karvir", "Panhala", "Radhanagari", "Shahuwadi", "Shirol"],
    "Latur": ["Ahmadpur", "Ausa", "Chakur", "Deoni", "Jalkot", "Latur", "Nilanga", "Renapur",
              "Shirur Anantpal", "Udgir"],
    "Mumbai City": [],
    "Mumbai Suburban": ["Andheri", "Borivali", "Kurla"],
    "Nagpur": ["Bhiwapur", "Hingna", "Kalmeshwar", "Kamptee", "Katol", "Kuhi", "Mauda", "Nagpur Rural",
               "Nagpur Urban", "Narkhed", "Parseoni", "Ramtek", "Savner", "Umred"],
    "Nanded": ["Ardhapur", "Bhokar", "Biloli", "Deglur", "Dharmabad", "Hadgaon", "Himayatnagar", "Kandhar",
               "Kinwat", "Loha", "Mahur", "Mudkhed", "Mukhed", "Naigaon", "Nanded", "Umri"],
    "Nandurbar": ["Akkalkuwa", "Akrani", "Nandurbar", "Navapur", "Shahada", "Taloda"],
    "Nashik": ["Baglan", "Chandwad", "Deola", "Dindori", "Igatpuri", "Kalwan", "Malegaon", "Nandgaon",
               "Nashik", "Niphad", "Peth", "Sinnar", "Surgana", "Trimbakeshwar", "Yeola"],
    "Palghar": ["Dahanu", "Jawhar", "Mokhada", "Palghar", "Talasari", "Vasai", "Vikramgad", "Wada"],
    "Parbhani": ["Gangakhed", "Jintur", "Manwat", "Palam", "Parbhani", "Pathri", "Purna", "Sailu", "Sonpeth"],
    "Pune": ["Ambegaon", "Baramati", "Bhor", "Daund", "Haveli", "Indapur", "Junnar", "Khed", "Maval",
             "Mulshi", "Pune City", "Purandar", "Shirur", "Velhe"],
    "Raigad": ["Alibag", "Karjat", "Khalapur", "Mahad", "Mangaon", "Mhasla", "Murud", "Panvel", "Pen",
               "Poladpur", "Roha", "Shrivardhan", "Sudhagad", "Tala", "Uran"],
    "Ratnagiri": ["Chiplun", "Dapoli", "Guhagar", "Khed", "Lanja", "Mandangad", "Rajapur", "Ratnagiri",
                  "Sangameshwar"],
    "Sangli": ["Atpadi", "Jat", "Kadegaon", "Kavathe Mahankal", "Khanapur", "Miraj", "Palus", "Shirala",
               "Tasgaon", "Walwa"],
    "Satara": ["Jaoli", "Karad", "Khandala", "Khatav", "Koregaon", "Mahabaleshwar", "Man", "Patan",
               "Phaltan", "Satara", "Wai"],
    "Sindhudurg": ["Devgad", "Dodamarg", "Kankavli", "Kudal", "Malvan", "Sawantwadi", "Vaibhavwadi",
                   "Vengurla"],
    "Solapur": ["Akkalkot", "Barshi", "Karmala", "Madha", "Malshiras", "Mangalwedha", "Mohol", "Pandharpur",
                "Sangole", "Solapur North", "Solapur South"],
    "Thane": ["Ambarnath", "Bhiwandi", "Kalyan", "Murbad", "Shahapur", "Thane", "Ulhasnagar"],
    "Wardha": ["Arvi", "Ashti", "Deoli", "Hinganghat", "Karanja", "Samudrapur", "Seloo", "Wardha"],
    "Washim": ["Karanja", "Malegaon", "Mangrulpir", "Manora", "Risod", "Washim"],
    "Yavatmal": ["Arni", "Babhulgaon", "Darwha", "Digras", "Ghatanji", "Kalamb", "Kelapur", "Mahagaon",
                 "Maregaon", "Ner", "Pusad", "Ralegaon", "Umarkhed", "Wani", "Yavatmal", "Zari Jamani"],
}

# The main town of a taluka when it differs from the taluka name - searched as well,
# because Google knows the town name better than the taluka name.
TALUKA_HQ: dict[tuple[str, str], str] = {
    ("Nashik", "Baglan"): "Satana",
    ("Sangli", "Khanapur"): "Vita",
    ("Sangli", "Walwa"): "Islampur",
    ("Yavatmal", "Kelapur"): "Pandharkawada",
    ("Nandurbar", "Akrani"): "Dhadgaon",
    ("Pune", "Haveli"): "Loni Kalbhor",
    ("Pune", "Khed"): "Rajgurunagar",
    ("Pune", "Maval"): "Vadgaon Maval",
    ("Pune", "Velhe"): "Vinzar",
    ("Raigad", "Sudhagad"): "Pali",
    ("Satara", "Jaoli"): "Medha",
    ("Satara", "Man"): "Dahiwadi",
    ("Satara", "Khatav"): "Vaduj",
    ("Kolhapur", "Karvir"): "Kolhapur",
    ("Kolhapur", "Hatkanangle"): "Ichalkaranji",
    ("Kolhapur", "Bhudargad"): "Gargoti",
    ("Hingoli", "Basmat"): "Basmath",
    ("Gadchiroli", "Desaiganj"): "Wadsa",
    ("Wardha", "Karanja"): "Karanja Ghadge",
    ("Washim", "Karanja"): "Karanja Lad",
    ("Ratnagiri", "Sangameshwar"): "Devrukh",
}

# Dense cities: a single "xerox in Pune" search returns at most 60 places, so big
# cities are also searched area by area.
CITY_AREAS: dict[str, list[str]] = {
    "Mumbai City": ["Colaba", "Fort", "Kalbadevi", "Girgaon", "Grant Road", "Byculla", "Mazgaon", "Tardeo",
                    "Malabar Hill", "Mumbai Central", "Lower Parel", "Worli", "Parel", "Sewri", "Dadar",
                    "Matunga", "Mahim", "Wadala", "Sion", "Dharavi", "Chinchpokli", "Nagpada"],
    "Mumbai Suburban": ["Bandra", "Khar", "Santacruz", "Vile Parle", "Andheri East", "Andheri West",
                        "Jogeshwari", "Goregaon", "Malad", "Kandivali", "Borivali", "Dahisar", "Kurla",
                        "Ghatkopar", "Vikhroli", "Bhandup", "Mulund", "Chembur", "Govandi", "Mankhurd", "Powai"],
    "Pune": ["Shivajinagar Pune", "Kothrud", "Deccan Gymkhana", "Swargate", "Pune Camp", "Hadapsar", "Kharadi",
             "Viman Nagar", "Yerawada", "Wakad", "Hinjewadi", "Pimpri", "Chinchwad", "Akurdi", "Nigdi",
             "Bhosari", "Aundh", "Baner", "Pashan", "Warje", "Katraj", "Bibwewadi", "Kondhwa", "Wanowrie",
             "Sinhagad Road", "Dhankawadi", "Wagholi", "Chakan", "Talegaon Dabhade", "Pimple Saudagar"],
    "Thane": ["Thane West", "Kalwa", "Mumbra", "Dombivli", "Kalyan West", "Kalyan East", "Ulhasnagar",
              "Ambernath", "Badlapur", "Bhiwandi", "Mira Road", "Bhayandar", "Vashi", "Nerul", "Airoli",
              "Ghansoli", "Kopar Khairane", "Titwala"],
    "Palghar": ["Virar", "Nalasopara", "Vasai Road", "Boisar"],
    "Raigad": ["Kharghar", "Kamothe", "Kalamboli", "New Panvel"],
    "Nagpur": ["Sitabuldi", "Dharampeth", "Sadar Nagpur", "Itwari", "Mahal Nagpur", "Manish Nagar",
               "Pratap Nagar", "Wardhaman Nagar", "Nandanvan", "Jaripatka", "Gandhibagh", "Trimurti Nagar",
               "Koradi", "Wadi Nagpur", "Hudkeshwar"],
    "Nashik": ["Nashik Road", "Panchavati", "CIDCO Nashik", "Satpur", "Gangapur Road Nashik",
               "College Road Nashik", "Deolali Camp", "Indira Nagar Nashik"],
    "Chhatrapati Sambhajinagar": ["CIDCO Chhatrapati Sambhajinagar", "Osmanpura", "Kranti Chowk",
                                  "Garkheda", "Waluj", "Jalna Road Chhatrapati Sambhajinagar", "Cantonment"],
    "Kolhapur": ["Rajarampuri", "Shahupuri", "Laxmipuri", "Jaysingpur"],
    "Solapur": ["Solapur city", "Akkalkot Road Solapur", "Hotgi Road Solapur"],
    "Amravati": ["Rajapeth Amravati", "Badnera", "Camp Amravati"],
    "Ahilyanagar": ["Savedi", "Kedgaon", "Bhingar"],
}


def search_talukas(district: str) -> list[str]:
    return list(MAHARASHTRA_TALUKAS.get(district, []))


def taluka_hq(district: str, taluka: str) -> str | None:
    return TALUKA_HQ.get((district, taluka))
