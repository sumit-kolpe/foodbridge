"""
02_generate_synthetic_raw.py - Generate the synthetic *raw* operational data.

The public Philadelphia dataset contains real recipient sites but no surplus
donations, requests or allocations, so these are simulated (see Project
Outline s.6). Generation is reproducible (seed 20261019).

The raw files deliberately look like exports from a real intake system
(simulated source noise), so the cleaning step in 03 has real work to do:
  * duplicate organisation registrations (name/address/ZIP variants)
  * inconsistent category labels, quantity text ("45 servings"),
    mixed timestamp formats
  * invalid rows (non-positive quantity, expiry before posting,
    unknown organisation) and double-submitted records
Ground truth for injected duplicates is saved so ER precision/recall can be
measured. Pass --no-noise to generate clean raw files instead.

Outputs (data/raw/synthetic/):
  food_categories.csv, org_registry_raw.csv, donations_raw.csv,
  requests_raw.csv, registry_duplicate_truth.csv, org_profiles.csv
"""

import argparse

import numpy as np
import pandas as pd

from common import (AS_OF, CITY, INTERIM_DIR, PHILLY_ZIPS, SEED, START,
                    SYN_RAW_DIR)

# ---------------------------------------------------------------------------
# Scale (Project Outline s.6.6)
# ---------------------------------------------------------------------------
TARGET_ORGS = 1000
N_BOTH = 35
N_SYN_RECIPIENTS = 120
N_DONATIONS = 150_000
N_REQUESTS = 120_000

# ---------------------------------------------------------------------------
# Food categories: (name, storage_type, shelf-life days (min,max), description)
# ---------------------------------------------------------------------------
CATEGORIES = [
    ("Prepared Hot Meals", "refrigerated", (0.4, 1.5), "Cooked entrees and sides ready to reheat and serve"),
    ("Sandwiches & Wraps", "refrigerated", (1, 3), "Pre-made sandwiches, wraps and cold boxed meals"),
    ("Salads", "refrigerated", (1, 3), "Packaged green, grain and pasta salads"),
    ("Deli & Prepared Proteins", "refrigerated", (2, 6), "Sliced deli meats, rotisserie chicken, cooked proteins"),
    ("Fresh Fruit", "refrigerated", (3, 12), "Whole and cut fresh fruit"),
    ("Fresh Vegetables", "refrigerated", (3, 12), "Fresh vegetables and leafy greens"),
    ("Fresh Meat & Poultry", "refrigerated", (1, 4), "Raw meat and poultry, kept cold"),
    ("Fresh Seafood", "refrigerated", (1, 3), "Raw fish and shellfish, kept cold"),
    ("Milk", "refrigerated", (5, 12), "Fluid milk and milk alternatives"),
    ("Cheese & Yogurt", "refrigerated", (7, 30), "Cheese, yogurt and other cultured dairy"),
    ("Eggs", "refrigerated", (14, 35), "Shell eggs"),
    ("Bread & Rolls", "shelf-stable", (2, 6), "Loaves, rolls, bagels and tortillas"),
    ("Pastries & Desserts", "shelf-stable", (1, 4), "Muffins, pastries, cakes and cookies"),
    ("Frozen Meals", "frozen", (30, 180), "Frozen entrees and ready meals"),
    ("Frozen Meat & Poultry", "frozen", (30, 180), "Frozen raw meat, poultry and fish"),
    ("Frozen Fruits & Vegetables", "frozen", (60, 240), "Frozen produce"),
    ("Canned Fruits & Vegetables", "shelf-stable", (180, 720), "Canned and jarred produce"),
    ("Canned Proteins & Beans", "shelf-stable", (180, 720), "Canned tuna, chicken, beans and legumes"),
    ("Rice, Pasta & Grains", "shelf-stable", (180, 540), "Dry rice, pasta, oats and grains"),
    ("Breakfast Cereal", "shelf-stable", (90, 360), "Boxed cereal and granola"),
    ("Soups & Broths", "shelf-stable", (180, 540), "Canned or boxed soups and broths"),
    ("Snacks", "shelf-stable", (60, 270), "Crackers, chips, bars and nuts"),
    ("Beverages & Juices", "shelf-stable", (30, 270), "Water, juice and other drinks"),
    ("Baby Food & Formula", "shelf-stable", (90, 360), "Infant formula and baby food"),
    ("Condiments, Sauces & Oils", "shelf-stable", (90, 540), "Sauces, spreads, oils and seasonings"),
]
CAT_NAMES = [c[0] for c in CATEGORIES]
C = {n: i for i, n in enumerate(CAT_NAMES)}


def W(pairs):
    w = np.full(len(CATEGORIES), 0.02)
    for name, v in pairs:
        w[C[name]] = v
    return w


# donor business type: share, median servings, sigma, category weights
DONOR_TYPES = {
    "restaurant":  (0.30, 28, 0.55, W([("Prepared Hot Meals", 5), ("Sandwiches & Wraps", 2), ("Salads", 1.5),
                                      ("Deli & Prepared Proteins", 1), ("Bread & Rolls", 1), ("Pastries & Desserts", .8),
                                      ("Fresh Vegetables", .6), ("Fresh Meat & Poultry", .4)])),
    "grocery":     (0.18, 75, 0.6, W([("Fresh Fruit", 3), ("Fresh Vegetables", 3), ("Milk", 1.5), ("Cheese & Yogurt", 1.2),
                                     ("Eggs", 1), ("Bread & Rolls", 1.5), ("Fresh Meat & Poultry", 1), ("Deli & Prepared Proteins", 1),
                                     ("Canned Fruits & Vegetables", .8), ("Breakfast Cereal", .6), ("Snacks", .6),
                                     ("Frozen Meals", .6), ("Beverages & Juices", .5), ("Baby Food & Formula", .3)])),
    "bakery":      (0.10, 40, 0.5, W([("Bread & Rolls", 5), ("Pastries & Desserts", 4)])),
    "cafeteria":   (0.12, 65, 0.5, W([("Prepared Hot Meals", 4), ("Sandwiches & Wraps", 2), ("Salads", 1.5),
                                     ("Fresh Fruit", 1), ("Milk", 1), ("Pastries & Desserts", .6)])),
    "caterer":     (0.08, 60, 0.55, W([("Prepared Hot Meals", 4), ("Sandwiches & Wraps", 1.5), ("Salads", 1.5),
                                      ("Pastries & Desserts", 1), ("Deli & Prepared Proteins", 1)])),
    "farm":        (0.06, 55, 0.6, W([("Fresh Vegetables", 4), ("Fresh Fruit", 3), ("Eggs", 1.2), ("Cheese & Yogurt", .5)])),
    "distributor": (0.08, 160, 0.6, W([("Canned Fruits & Vegetables", 2), ("Canned Proteins & Beans", 2),
                                      ("Rice, Pasta & Grains", 2), ("Breakfast Cereal", 1), ("Soups & Broths", 1.2),
                                      ("Frozen Meals", 1), ("Frozen Meat & Poultry", 1), ("Frozen Fruits & Vegetables", 1),
                                      ("Beverages & Juices", 1), ("Condiments, Sauces & Oils", .7),
                                      ("Baby Food & Formula", .5), ("Snacks", .8), ("Fresh Seafood", .3)])),
    "hotel":       (0.05, 45, 0.5, W([("Prepared Hot Meals", 3), ("Pastries & Desserts", 2), ("Bread & Rolls", 1),
                                     ("Fresh Fruit", 1.2), ("Cheese & Yogurt", .6)])),
    "corner_store": (0.03, 18, 0.5, W([("Snacks", 3), ("Beverages & Juices", 3), ("Bread & Rolls", 1.5),
                                       ("Sandwiches & Wraps", 1), ("Milk", .7)])),
}

# recipient profile: median servings requested, sigma, category weights
RECIPIENT_PROFILES = {
    "pantry":    (95, 0.6, W([("Canned Fruits & Vegetables", 2.5), ("Canned Proteins & Beans", 2.5), ("Rice, Pasta & Grains", 2.5),
                              ("Fresh Fruit", 2), ("Fresh Vegetables", 2.5), ("Milk", 1.5), ("Eggs", 1.5), ("Bread & Rolls", 1.2),
                              ("Breakfast Cereal", 1.5), ("Soups & Broths", 1.2), ("Frozen Meat & Poultry", 1.2),
                              ("Baby Food & Formula", 1), ("Cheese & Yogurt", .8), ("Frozen Fruits & Vegetables", .8),
                              ("Condiments, Sauces & Oils", .5), ("Snacks", .5), ("Beverages & Juices", .5)])),
    "meal_site": (110, 0.55, W([("Prepared Hot Meals", 4), ("Sandwiches & Wraps", 2), ("Fresh Vegetables", 1.5),
                               ("Fresh Meat & Poultry", 1.5), ("Frozen Meat & Poultry", 1.2), ("Bread & Rolls", 1.2),
                               ("Salads", 1), ("Fresh Fruit", 1), ("Rice, Pasta & Grains", 1), ("Milk", .8),
                               ("Deli & Prepared Proteins", 1), ("Frozen Meals", .8)])),
    "senior":    (70, 0.5, W([("Prepared Hot Meals", 3), ("Soups & Broths", 2), ("Milk", 1.5), ("Fresh Fruit", 1.5),
                             ("Frozen Meals", 1.5), ("Bread & Rolls", 1), ("Cheese & Yogurt", 1), ("Sandwiches & Wraps", 1)])),
    "fridge":    (40, 0.5, W([("Fresh Fruit", 2), ("Fresh Vegetables", 2), ("Sandwiches & Wraps", 2), ("Milk", 1.5),
                             ("Bread & Rolls", 1.5), ("Prepared Hot Meals", 1), ("Eggs", 1), ("Pastries & Desserts", 1)])),
    "shelter":   (120, 0.5, W([("Prepared Hot Meals", 3), ("Frozen Meals", 2), ("Breakfast Cereal", 1.5), ("Milk", 1.5),
                              ("Fresh Fruit", 1), ("Bread & Rolls", 1.2), ("Rice, Pasta & Grains", 1), ("Baby Food & Formula", .8),
                              ("Frozen Meat & Poultry", 1)])),
}

NEIGHBORHOODS = [
    "Fishtown", "Northern Liberties", "Kensington", "Port Richmond", "Manayunk", "Roxborough",
    "East Falls", "Germantown", "Mt. Airy", "Chestnut Hill", "Fairmount", "Spring Garden",
    "Callowhill", "Old City", "Society Hill", "Queen Village", "Bella Vista", "Graduate Hospital",
    "Rittenhouse", "Logan Square", "Washington Square", "Point Breeze", "Passyunk", "Pennsport",
    "Grays Ferry", "Kingsessing", "Cedar Park", "Spruce Hill", "Powelton", "Mantua", "Brewerytown",
    "Strawberry Mansion", "Nicetown", "Hunting Park", "Frankford", "Mayfair", "Tacony", "Holmesburg",
    "Fox Chase", "Bustleton", "Somerton", "Olney", "Oak Lane", "Wynnefield", "Overbrook", "Eastwick",
    "Whitman", "Juniata", "Logan", "Tioga", "Fern Rock", "Lawncrest", "Wissinoming", "Bridesburg",
]
SURNAMES = [
    "Rossi", "Nguyen", "Kim", "Patel", "Garcia", "O'Brien", "Murphy", "Johnson", "Williams", "Chen",
    "Lopez", "Haddad", "Kowalski", "DiMarco", "Sullivan", "Okafor", "Rivera", "Santos", "Park",
    "Singh", "Cohen", "Russo", "Moreno", "Brennan", "Tran", "Ali", "Ramirez", "Schmidt", "Greco",
    "Bianchi", "Mensah", "Delgado", "Romano", "Walsh", "Le", "Ortiz", "Abboud", "Novak", "Reyes", "Byrne",
]
ADJ = ["Copper", "Golden", "Rusty", "Little", "Green", "Blue", "Corner", "Hungry", "Lucky",
       "Silver", "Red Brick", "Old Mill", "Iron", "Maple", "Harvest", "Sunny", "Cobblestone"]
NOUN = ["Spoon", "Fork", "Table", "Skillet", "Oven", "Pot", "Lantern", "Ladle", "Hearth", "Kettle"]
REGION = ["Harbor", "Valley", "Keystone", "Delaware", "Liberty", "Schuylkill", "Penn", "Riverside"]

NAME_PATTERNS = {
    "restaurant": ["{s}'s {r}", "{n} {r2}", "The {a} {o}", "{a} {o} {r}"],
    "grocery": ["{n} Fresh Market", "{s} Family Grocers", "{n} Food Co-op", "{a} Basket Supermarket"],
    "bakery": ["{s}'s Bakery", "{n} Bread Co.", "{a} Crust Bakehouse", "{a} Oven Bakery"],
    "cafeteria": ["{n} {inst} Dining Services", "{a} {inst} Cafeteria"],
    "caterer": ["{s} Catering", "{n} Events & Catering", "{a} {o} Catering Co."],
    "farm": ["{s} Family Farm", "{n} Farmers Market Stand", "{a} Acres Farm"],
    "distributor": ["{reg} Food Distributors", "{s} Wholesale Foods", "{a} {reg} Food Supply"],
    "hotel": ["{n} {h}", "The {a} {h}"],
    "corner_store": ["{n} Corner Market", "{s}'s Deli & Grocery", "{a} Mini Mart"],
    "recipient": ["{n} {rc}", "{a} {rc}", "{s} House {rc}"],
    "both": ["{n} {b}", "{a} {b}"],
}
R1 = ["Trattoria", "Kitchen", "Grill", "Diner", "Bistro", "Cantina", "Eatery"]
R2 = ["Taqueria", "Noodle House", "Grill", "Bistro", "Pizza Co.", "Cafe", "Smokehouse", "Pho", "Halal Grill"]
INST = ["Medical Center", "Community Hospital", "College", "University Campus", "Corporate Center", "Senior Living"]
HOTEL = ["Inn", "Hotel", "Suites", "Guest House"]
RC = ["Community Kitchen", "Family Shelter", "Food Pantry", "Youth Center Pantry", "Recovery House",
      "Mutual Aid Pantry", "Men's Shelter", "Women's Shelter", "Outreach Kitchen", "Student Pantry"]
BOTH = ["Community Church", "Neighborhood Center", "Masjid Food Ministry", "Synagogue Kitchen",
        "Community Garden", "Parish Kitchen"]
RC_PROFILE = {"Community Kitchen": "meal_site", "Family Shelter": "shelter", "Food Pantry": "pantry",
              "Youth Center Pantry": "pantry", "Recovery House": "shelter", "Mutual Aid Pantry": "pantry",
              "Men's Shelter": "shelter", "Women's Shelter": "shelter", "Outreach Kitchen": "meal_site",
              "Student Pantry": "pantry"}

STREETS = ["Market St", "Chestnut St", "Walnut St", "Spruce St", "Pine St", "South St", "Arch St",
           "Race St", "Vine St", "Spring Garden St", "Girard Ave", "Lancaster Ave", "Baltimore Ave",
           "Germantown Ave", "Frankford Ave", "Ridge Ave", "E Passyunk Ave", "Washington Ave",
           "Snyder Ave", "Oregon Ave", "Castor Ave", "Cottman Ave", "Aramingo Ave", "Kensington Ave",
           "W Allegheny Ave", "W Lehigh Ave", "E Erie Ave", "W Chelten Ave", "Haverford Ave",
           "Main St", "Fairmount Ave", "Woodland Ave", "Bustleton Ave", "Torresdale Ave",
           "N Broad St", "S Broad St", "N 5th St", "S 9th St", "N 22nd St", "S 52nd St", "N 63rd St"]
# donors cluster in commercial ZIPs
DONOR_ZIP_BOOST = {"19102": 4, "19103": 5, "19104": 4, "19106": 4, "19107": 5, "19123": 3,
                   "19146": 3, "19147": 4, "19130": 3, "19125": 3, "19148": 2, "19128": 2, "19127": 2}

# ---------------------------------------------------------------------------
rng = np.random.default_rng(SEED)
DAYS = pd.date_range(START.normalize(), AS_OF.normalize(), freq="D")
T = len(DAYS)


def day_weights(kind: str) -> np.ndarray:
    """Relative daily volume: platform growth x seasonality x weekday."""
    t = np.arange(T) / (T - 1)
    growth = 0.55 + 0.65 * t                                   # adoption ramp
    m, d, wd = DAYS.month.values, DAYS.day.values, DAYS.dayofweek.values
    holiday = ((m == 11) & (d >= 15)) | (m == 12) | ((m == 1) & (d <= 5))
    if kind == "donation":
        season = 1 + 0.30 * holiday
        week = np.array([0.9, 0.95, 1.0, 1.0, 1.15, 1.2, 0.8])[wd]
    else:
        season = 1 + 0.15 * np.isin(m, [6, 7, 8]) + 0.25 * np.isin(m, [12, 1, 2])
        week = np.array([1.25, 1.15, 1.05, 1.0, 0.95, 0.6, 0.5])[wd]
    return growth * season * week


def unique_names(kind: str, n: int, used: set) -> list[str]:
    out = []
    while len(out) < n:
        p = rng.choice(NAME_PATTERNS[kind])
        name = p.format(s=rng.choice(SURNAMES), n=rng.choice(NEIGHBORHOODS), a=rng.choice(ADJ),
                        o=rng.choice(NOUN), r=rng.choice(R1), r2=rng.choice(R2), inst=rng.choice(INST),
                        reg=rng.choice(REGION), h=rng.choice(HOTEL), rc=rng.choice(RC), b=rng.choice(BOTH))
        if name not in used:
            used.add(name)
            out.append(name)
    return out


def random_address() -> str:
    return f"{int(rng.integers(100, 9900))} {rng.choice(STREETS)}"


def fake_phone() -> str:
    # 555 exchange: clearly fictional numbers
    return f"({rng.choice(['215', '267', '445'])}) 555-{int(rng.integers(0, 10000)):04d}"


def slug(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())[:24]


# ---------------------------------------------------------------------------
# Organisations
# ---------------------------------------------------------------------------
def build_registry(philly: pd.DataFrame):
    n_donors = TARGET_ORGS - len(philly) - N_SYN_RECIPIENTS - N_BOTH
    used = set(philly.organization_name)
    rows = []
    dtypes = list(DONOR_TYPES)
    shares = np.array([DONOR_TYPES[t][0] for t in dtypes])
    donor_types = rng.choice(dtypes, size=n_donors, p=shares / shares.sum())
    donor_zip_w = np.array([DONOR_ZIP_BOOST.get(z, 1.0) for z in PHILLY_ZIPS])
    rec_zip_counts = philly.zip_code.value_counts()
    rec_zip_w = np.array([rec_zip_counts.get(z, 0) + 1.0 for z in PHILLY_ZIPS])

    for t in dtypes:
        k = int((donor_types == t).sum())
        for name in unique_names(t, k, used):
            rows.append(dict(org_role="donor", business_type=t, profile=None, name=name,
                             zip=rng.choice(PHILLY_ZIPS, p=donor_zip_w / donor_zip_w.sum())))
    for name in unique_names("recipient", N_SYN_RECIPIENTS, used):
        rc = next(r for r in RC if name.endswith(r))
        rows.append(dict(org_role="recipient", business_type=None, profile=RC_PROFILE[rc], name=name,
                         zip=rng.choice(PHILLY_ZIPS, p=rec_zip_w / rec_zip_w.sum())))
    for name in unique_names("both", N_BOTH, used):
        rows.append(dict(org_role="both", business_type="community_org", profile="pantry", name=name,
                         zip=rng.choice(PHILLY_ZIPS)))
    reg = pd.DataFrame(rows)
    reg["address"] = [random_address() for _ in range(len(reg))]
    reg["phone"] = [fake_phone() for _ in range(len(reg))]
    reg["email"] = [f"{('donate' if r != 'recipient' else 'info')}@{slug(n)}.example.org"
                    for r, n in zip(reg.org_role, reg.name)]
    reg["status"] = np.where(rng.random(len(reg)) < 0.04, "inactive", "active")
    # platform onboarding date: early adopters + gradual growth
    join = START + pd.to_timedelta(rng.beta(1.2, 2.5, len(reg)) * (T * 0.7), unit="D")
    reg["joined"] = join.normalize()
    # inactive orgs left the platform at some point
    left = reg.joined + pd.to_timedelta(rng.uniform(60, 400, len(reg)), unit="D")
    reg["left"] = np.where(reg.status == "inactive", left.clip(upper=AS_OF - pd.Timedelta(days=30)), pd.NaT)
    reg["left"] = pd.to_datetime(reg["left"])
    reg["activity"] = rng.lognormal(0, 0.9, len(reg))
    reg = reg.sample(frac=1, random_state=SEED).reset_index(drop=True)
    reg.insert(0, "registry_id", np.arange(1001, 1001 + len(reg)))
    reg["raw_key"] = "SYN-" + reg.registry_id.astype(str)
    return reg


# ---------------------------------------------------------------------------
# Activity (donations / requests)
# ---------------------------------------------------------------------------
def spread(total: int, weight: np.ndarray) -> np.ndarray:
    return rng.multinomial(total, weight / weight.sum())


def sample_days(n, wday, lo: pd.Timestamp, hi: pd.Timestamp):
    i0 = max(0, (lo.normalize() - DAYS[0]).days)
    i1 = min(T, (hi.normalize() - DAYS[0]).days + 1)
    w = wday[i0:i1]
    return DAYS[i0 + rng.choice(len(w), size=n, p=w / w.sum())]


def gen_donations(donors: pd.DataFrame) -> pd.DataFrame:
    wday = day_weights("donation")
    end = donors.left.fillna(AS_OF)
    span = (end - donors.joined).dt.days.clip(lower=1)
    counts = spread(int(N_DONATIONS * 1.01), donors.activity.values * span.values)
    shelf = np.array([c[2] for c in CATEGORIES])
    parts = []
    for (_, d), n, hi in zip(donors.iterrows(), counts, end):
        if n == 0:
            continue
        share, med, sig, cw = DONOR_TYPES.get(d.business_type, (0, 35, 0.6, W([("Bread & Rolls", 2),
                                              ("Fresh Vegetables", 2), ("Pastries & Desserts", 1.5),
                                              ("Prepared Hot Meals", 1)])))
        pref = cw * rng.lognormal(0, 0.5, len(cw))                 # donor-specific taste
        cat = rng.choice(len(CATEGORIES), size=n, p=pref / pref.sum())
        day = sample_days(n, wday, d.joined, hi)
        hour = np.clip(rng.normal(15, 4, n), 6, 23.5)
        donated = day + pd.to_timedelta(hour * 3600 + rng.integers(0, 60, n), unit="s")
        qty = np.clip(np.round(rng.lognormal(np.log(med), sig, n)), 1, 1500).astype(int)
        parts.append(pd.DataFrame({"donor_key": d.raw_key, "cat": cat, "quantity": qty, "donated_at": donated}))
    don = pd.concat(parts, ignore_index=True)
    lo, hi = shelf[don.cat, 0], shelf[don.cat, 1]
    life_h = rng.uniform(lo, hi) * 24
    don["expires_at"] = don.donated_at + pd.to_timedelta(life_h, unit="h")
    # pickup window: perishable -> 2-24 h; otherwise 1-7 days; never after expiry
    win = np.where(life_h <= 72, rng.uniform(2, 24, len(don)), rng.uniform(24, 168, len(don)))
    win = np.minimum(win, life_h * 0.9)
    don["pickup_deadline"] = don.donated_at + pd.to_timedelta(win, unit="h")
    # nothing posted after the snapshot time
    don = don[don.donated_at <= AS_OF].sample(n=N_DONATIONS, random_state=SEED)
    return don.sort_values("donated_at").reset_index(drop=True)


def gen_requests(recips: pd.DataFrame) -> pd.DataFrame:
    wday = day_weights("request")
    end = recips.left.fillna(AS_OF)
    span = (end - recips.joined).dt.days.clip(lower=1)
    counts = spread(int(N_REQUESTS * 1.01), recips.activity.values * span.values)
    parts = []
    for (_, r), n, hi in zip(recips.iterrows(), counts, end):
        if n == 0:
            continue
        med, sig, cw = RECIPIENT_PROFILES[r.profile]
        pref = cw * rng.lognormal(0, 0.5, len(cw))
        cat = rng.choice(len(CATEGORIES), size=n, p=pref / pref.sum())
        day = sample_days(n, wday, r.joined, hi)
        hour = np.clip(rng.normal(11, 3, n), 7, 21)
        req_at = day + pd.to_timedelta(hour * 3600 + rng.integers(0, 60, n), unit="s")
        qty = np.clip(np.round(rng.lognormal(np.log(med), sig, n)), 5, 2000).astype(int)
        perishable = np.isin(cat, [C["Prepared Hot Meals"], C["Sandwiches & Wraps"], C["Salads"]])
        lead_h = np.where(perishable, rng.uniform(12, 96, n), rng.uniform(48, 336, n))
        # requests from real sites may cite any of the site's raw source rows
        keys = rng.choice(r.raw_keys, size=n) if isinstance(r.raw_keys, list) else r.raw_key
        parts.append(pd.DataFrame({"recipient_key": keys, "cat": cat, "requested_quantity": qty,
                                   "requested_at": req_at,
                                   "needed_by": req_at + pd.to_timedelta(lead_h, unit="h")}))
    req = pd.concat(parts, ignore_index=True)
    req = req[req.requested_at <= AS_OF].sample(n=N_REQUESTS, random_state=SEED)
    return req.sort_values("requested_at").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Simulated source noise
# ---------------------------------------------------------------------------
CAT_VARIANTS = {
    "Prepared Hot Meals": ["prepared hot meals", "Hot Meals", "PREPARED HOT MEALS", "Prepared Meals (Hot)"],
    "Sandwiches & Wraps": ["Sandwiches and Wraps", "sandwiches & wraps", "Sandwiches/Wraps"],
    "Fresh Fruit": ["fresh fruits", "Produce - Fruit", "FRESH FRUIT"],
    "Fresh Vegetables": ["fresh veggies", "Produce - Vegetables", "Fresh Vegetable"],
    "Bread & Rolls": ["Bread and Rolls", "bread & rolls", "Bakery - Bread"],
    "Pastries & Desserts": ["Pastries and Desserts", "Bakery - Pastries", "desserts"],
    "Milk": ["MILK", "Dairy - Milk", "milk "],
    "Canned Fruits & Vegetables": ["Canned Fruit & Veg", "canned fruits and vegetables"],
    "Rice, Pasta & Grains": ["Rice/Pasta/Grains", "rice, pasta & grains", "Grains"],
}


def name_variant(name: str) -> str:
    """A realistic duplicate-registration spelling of an organisation name."""
    ops = [lambda s: s.upper(), lambda s: s.lower(), lambda s: s + " LLC", lambda s: s + ", Inc.",
           lambda s: s.replace("&", "and"), lambda s: s.replace("'", ""), lambda s: "  " + s + " ",
           lambda s: s.replace(" Co.", " Company")]
    s = rng.choice(ops)(name)
    if rng.random() < 0.25 and len(s) > 6:                      # typo: swap two letters
        i = int(rng.integers(1, len(s) - 2))
        s = s[:i] + s[i + 1] + s[i] + s[i + 2:]
    return s


def address_variant(addr: str) -> str:
    ops = [lambda s: s.replace(" St", " Street").replace(" Ave", " Avenue"),
           lambda s: s.replace(" St", " St.").replace(" Ave", " Ave."),
           lambda s: s.upper(), lambda s: s + " Suite " + str(int(rng.integers(1, 400))),
           lambda s: s.replace(" N ", " North ").replace(" S ", " South ")]
    return rng.choice(ops)(addr)


def zip_variant(z: str) -> str:
    return rng.choice([z, z + "-" + f"{int(rng.integers(1000, 9999))}", " " + z, z + ".0"])


def add_registry_noise(reg: pd.DataFrame, frac=0.05):
    """Duplicate registrations of ~5% of organisations (+ format noise)."""
    src = reg.sample(frac=frac, random_state=SEED + 1)
    dup = src.copy()
    dup["name"] = dup.name.map(name_variant)
    dup["address"] = dup.address.map(address_variant)
    dup["phone"] = np.where(rng.random(len(dup)) < 0.4, None, dup.phone)
    dup["registry_id"] = np.arange(reg.registry_id.max() + 1, reg.registry_id.max() + 1 + len(dup))
    dup["raw_key"] = "SYN-" + dup.registry_id.astype(str)
    truth = pd.DataFrame({"duplicate_registry_id": dup.registry_id.values,
                          "original_registry_id": src.registry_id.values})
    out = pd.concat([reg, dup], ignore_index=True)
    out["zip"] = out.zip.map(lambda z: zip_variant(z) if rng.random() < 0.15 else z)
    out["status"] = out.status.map(lambda s: rng.choice([s, s.upper(), s.title(), f" {s}"]))
    out["org_role"] = out.org_role.map(lambda s: rng.choice([s, s.title(), s.upper()]) if rng.random() < 0.2 else s)
    out["city"] = [rng.choice([CITY, "PHILADELPHIA", "Phila", "Philadelphia, PA"]) if rng.random() < 0.1 else CITY
                   for _ in range(len(out))]
    return out.sample(frac=1, random_state=SEED + 2).reset_index(drop=True), truth


def fmt_ts(ts: pd.Series, frac=0.02) -> pd.Series:
    s = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
    m = rng.random(len(s)) < frac
    s[m] = ts[m].dt.strftime("%m/%d/%Y %H:%M")
    return s


def noisy_activity(df, key_col, qty_col, ts_cols, dup_map: dict, prefix: str, valid_keys):
    """Format noise + invalid rows + double submissions for donations/requests."""
    n = len(df)
    df = df.copy()
    # route ~30% of activity of duplicated orgs through the duplicate registration
    if dup_map:
        m = df[key_col].isin(dup_map) & (rng.random(n) < 0.3)
        df.loc[m, key_col] = df.loc[m, key_col].map(dup_map)
    df["category_label"] = [rng.choice(CAT_VARIANTS[CAT_NAMES[c]]) if CAT_NAMES[c] in CAT_VARIANTS
                            and rng.random() < 0.04 else CAT_NAMES[c] for c in df.cat]
    q = df[qty_col].astype(str)
    m = rng.random(n) < 0.015
    q[m] = q[m] + " servings"
    df[qty_col] = q
    # invalid rows (added on top of the valid ones)
    bad = df.sample(n=int(n * 0.012), random_state=SEED + 3).copy()
    k = len(bad) // 3
    bad.iloc[:k, bad.columns.get_loc(qty_col)] = rng.choice(["0", "-5", "", "-20"], size=k)
    t0, t1 = ts_cols[0], ts_cols[1]
    bad.iloc[k:2 * k, bad.columns.get_loc(t1)] = (bad.iloc[k:2 * k][t0] - pd.Timedelta(hours=3)).values
    bad.iloc[2 * k:, bad.columns.get_loc(key_col)] = "SYN-" + pd.Series(
        rng.integers(90000, 99999, len(bad) - 2 * k)).astype(str).values
    # double submissions: same record re-sent minutes later under a new reference
    dups = df.sample(n=int(n * 0.004), random_state=SEED + 4).copy()
    out = pd.concat([df, bad, dups], ignore_index=True)
    out = out.sample(frac=1, random_state=SEED + 5).reset_index(drop=True)
    for c in ts_cols:
        out[c] = fmt_ts(out[c])
    out.insert(0, f"{prefix}_ref", [f"{prefix.upper()}-{i:07d}" for i in range(1, len(out) + 1)])
    return out.drop(columns="cat")


def main(noise: bool = True):
    philly = pd.read_csv(INTERIM_DIR / "philly_sites_clean.csv", dtype={"zip_code": str})
    reg = build_registry(philly)

    # categories reference table (curated, clean)
    pd.DataFrame([{"category_name": n, "storage_type": s, "description": d}
                  for n, s, _, d in CATEGORIES]).to_csv(SYN_RAW_DIR / "food_categories.csv", index=False)

    donors = reg[reg.org_role.isin(["donor", "both"])]
    don = gen_donations(donors)

    # recipients = active real Philly sites + synthetic recipients / both
    real = philly[philly.status == "active"].copy()

    def profile(st):
        st = st.split(";")
        if "Senior Meal Site" in st and len(st) == 1:
            return "senior"
        if "General Meal Site" in st:
            return "meal_site"
        return "pantry"
    real["profile"] = real.service_types.map(profile)
    real.loc[real.organization_name.str.contains("fridge", case=False), "profile"] = "fridge"
    real["raw_keys"] = real.source_objectids.map(lambda s: ["PHL-" + x for x in s.split(";")])
    real["raw_key"] = real.raw_keys.str[0]
    real["joined"] = START + pd.to_timedelta(rng.beta(1.0, 3.0, len(real)) * T * 0.5, unit="D")
    real["joined"] = real.joined.dt.normalize()
    real["left"] = pd.NaT
    real["activity"] = rng.lognormal(0, 0.8, len(real))
    syn_rec = reg[reg.org_role.isin(["recipient", "both"])].assign(raw_keys=None)
    recips = pd.concat([real[["raw_key", "raw_keys", "profile", "joined", "left", "activity"]],
                        syn_rec[["raw_key", "raw_keys", "profile", "joined", "left", "activity"]]],
                       ignore_index=True)
    req = gen_requests(recips)

    # save generation-time profile info (used for documentation / analysis)
    reg[["registry_id", "org_role", "business_type", "profile", "joined", "left"]].to_csv(
        SYN_RAW_DIR / "org_profiles.csv", index=False)

    if noise:
        reg_raw, truth = add_registry_noise(reg)
        dup_map = dict(zip("SYN-" + truth.original_registry_id.astype(str),
                           "SYN-" + truth.duplicate_registry_id.astype(str)))
    else:
        reg_raw, truth, dup_map = reg.assign(city=CITY), pd.DataFrame(
            columns=["duplicate_registry_id", "original_registry_id"]), {}

    reg_out = reg_raw.rename(columns={"name": "org_name", "zip": "zip_code"})[
        ["registry_id", "org_name", "org_role", "address", "city", "zip_code", "phone", "email", "status"]]
    reg_out.to_csv(SYN_RAW_DIR / "org_registry_raw.csv", index=False)
    truth.to_csv(SYN_RAW_DIR / "registry_duplicate_truth.csv", index=False)

    if noise:
        don_raw = noisy_activity(don, "donor_key", "quantity", ["donated_at", "expires_at", "pickup_deadline"],
                                 dup_map, "don", None)
        req_raw = noisy_activity(req, "recipient_key", "requested_quantity", ["requested_at", "needed_by"],
                                 dup_map, "req", None)
    else:
        don_raw = don.assign(category_label=[CAT_NAMES[c] for c in don.cat]).drop(columns="cat")
        req_raw = req.assign(category_label=[CAT_NAMES[c] for c in req.cat]).drop(columns="cat")
    don_raw = don_raw[["don_ref", "donor_key", "category_label", "quantity", "donated_at",
                       "expires_at", "pickup_deadline"]] if noise else don_raw
    req_raw = req_raw[["req_ref", "recipient_key", "category_label", "requested_quantity",
                       "requested_at", "needed_by"]] if noise else req_raw
    don_raw.to_csv(SYN_RAW_DIR / "donations_raw.csv", index=False)
    req_raw.to_csv(SYN_RAW_DIR / "requests_raw.csv", index=False)

    print(f"registry: {len(reg)} orgs (+{len(truth)} duplicate registrations) | "
          f"donations: {len(don)} valid -> {len(don_raw)} raw | "
          f"requests: {len(req)} valid -> {len(req_raw)} raw")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-noise", action="store_true", help="write clean raw files")
    main(noise=not ap.parse_args().no_noise)
