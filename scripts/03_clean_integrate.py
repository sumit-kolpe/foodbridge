"""
03_clean_integrate.py - Clean the raw synthetic files, resolve duplicate
organisation registrations, and integrate them with the cleaned Philadelphia
sites into the Organization / FoodCategory / FoodDonation / RecipientRequest
tables (statuses are derived later in 04 once allocations exist).

Inputs : data/interim/philly_sites_clean.csv, data/interim/philly_er_map.csv
         data/raw/synthetic/*.csv
Outputs: data/interim/{organization,food_category,donation_clean,request_clean}.csv
         data/interim/org_key_map.csv   raw source key -> organization_id
         reports/cleaning_report.md
"""

import re

import numpy as np
import pandas as pd

from common import (CITY, INTERIM_DIR, REPORT_DIR, SYN_RAW_DIR, clean_text,
                    contact_string, norm_status, norm_zip, parse_contact,
                    resolve_entities)

LOG: list[str] = []


def log(s=""):
    LOG.append(s)


# Hand-written mapping for category labels that normalisation alone cannot fix
# (built by inspecting value_counts() of the raw category_label column).
CATEGORY_SYNONYMS = {
    "hot meals": "prepared hot meals", "prepared meals hot": "prepared hot meals",
    "fresh fruits": "fresh fruit", "produce fruit": "fresh fruit",
    "fresh veggies": "fresh vegetables", "fresh vegetable": "fresh vegetables",
    "produce vegetables": "fresh vegetables",
    "bakery bread": "bread and rolls", "bakery pastries": "pastries and desserts",
    "desserts": "pastries and desserts", "dairy milk": "milk",
    "canned fruit and veg": "canned fruits and vegetables",
    "grains": "rice pasta and grains", "rice pasta grains": "rice pasta and grains",
    "sandwiches wraps": "sandwiches and wraps",
}


def cat_key(label) -> str:
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return ""
    s = str(label).lower().replace("&", " and ").replace("/", " ")
    s = " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())
    return CATEGORY_SYNONYMS.get(s, s)


def parse_qty(v) -> float:
    m = re.match(r"^\s*(-?\d+)", str(v)) if v is not None else None
    return float(m.group(1)) if m else np.nan


def parse_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="mixed", errors="coerce")


# ---------------------------------------------------------------------------
def build_organizations():
    philly = pd.read_csv(INTERIM_DIR / "philly_sites_clean.csv", dtype={"zip_code": str})
    pmap = pd.read_csv(INTERIM_DIR / "philly_er_map.csv")
    reg = pd.read_csv(SYN_RAW_DIR / "org_registry_raw.csv", dtype=str)
    truth = pd.read_csv(SYN_RAW_DIR / "registry_duplicate_truth.csv")

    log("## 1. Organization registry (synthetic donors / recipients)\n")
    log(f"* Raw registrations: {len(reg)}")
    reg["registry_id"] = reg.registry_id.astype(int)
    for c in ["org_name", "address", "phone", "email", "city", "org_role", "status"]:
        reg[c] = reg[c].map(clean_text)
    reg["zip5"] = reg.zip_code.map(norm_zip)
    reg["status_std"] = reg.status.map(norm_status)
    reg["role"] = reg.org_role.str.lower()
    reg["city_std"] = np.where(reg.city.str.lower().str.startswith("phila"), CITY, reg.city)
    reg["phone_std"] = reg.phone.map(lambda p: parse_contact(p)[0])
    log(f"* Standardised: ZIP formats ({(reg.zip_code != reg.zip5).sum()} fixed, e.g. "
        f"'19103-1234', '19103.0'), status case/whitespace, role case, "
        f"city spellings ({(reg.city != CITY).sum()} fixed: Phila / PHILADELPHIA / 'Philadelphia, PA').")

    # entity resolution (same routine as the Philadelphia data)
    reg["cluster"] = resolve_entities(reg, "registry_id", "org_name", "address")
    pred_pairs = set()
    for _, g in reg.groupby("cluster"):
        ids = sorted(g.registry_id)
        pred_pairs |= {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]}
    true_pairs = {tuple(sorted(p)) for p in truth[["duplicate_registry_id", "original_registry_id"]].values}
    tp = len(pred_pairs & true_pairs)
    prec = tp / len(pred_pairs) if pred_pairs else 1.0
    rec = tp / len(true_pairs) if true_pairs else 1.0
    log(f"* Entity resolution: {len(reg)} registrations -> {reg.cluster.nunique()} organisations. "
        f"Against the injected ground truth: precision {prec:.3f}, recall {rec:.3f} "
        f"({tp}/{len(true_pairs)} duplicate pairs found, {len(pred_pairs) - tp} false merges).")
    missed = truth[[tuple(sorted(p)) not in pred_pairs for p in
                    truth[["duplicate_registry_id", "original_registry_id"]].values]]
    if len(missed):
        names = reg.set_index("registry_id").org_name
        log("* Missed duplicates (kept as separate organisations):")
        for d, o in missed.values:
            log(f"  * '{names[o]}' vs '{names[d]}'")

    syn_orgs = []
    for cid, g in reg.groupby("cluster"):
        # master record = earliest registration that has a phone number
        g = g.assign(_p=g.phone_std.notna().astype(int)).sort_values(["_p", "registry_id"],
                                                                      ascending=[False, True])
        best = g.iloc[0]
        roles = set(g.role.dropna())
        role = "both" if "both" in roles or roles >= {"donor", "recipient"} else best.role
        syn_orgs.append({"cluster": cid, "organization_name": best.org_name, "organization_type": role,
                         "address": best.address, "city": best.city_std, "zip_code": best.zip5,
                         "contact_information": contact_string(best.phone_std, best.email),
                         "status": "active" if (g.status_std == "active").any() else "inactive"})
    syn = pd.DataFrame(syn_orgs).sort_values("cluster")

    # ---- combine with Philadelphia sites: real sites get ids 1..N ----
    philly = philly.sort_values("source_cluster_id").reset_index(drop=True)
    philly["organization_id"] = np.arange(1, len(philly) + 1)
    syn["organization_id"] = np.arange(len(philly) + 1, len(philly) + 1 + len(syn))
    cols = ["organization_id", "organization_name", "organization_type", "address", "city",
            "zip_code", "contact_information", "status"]
    org = pd.concat([philly.assign(organization_type="recipient")[cols], syn[cols]], ignore_index=True)

    # raw key -> organization_id
    pm = pmap.merge(philly[["source_cluster_id", "organization_id"]],
                    left_on="cluster", right_on="source_cluster_id")
    keys = pd.concat([
        pd.DataFrame({"raw_key": "PHL-" + pm.objectid.astype(str), "organization_id": pm.organization_id}),
        pd.DataFrame({"raw_key": "SYN-" + reg.registry_id.astype(str),
                      "organization_id": reg.cluster.map(syn.set_index("cluster").organization_id)}),
    ], ignore_index=True)

    # enriched side table (not part of the core schema): provenance + coordinates
    meta = pd.concat([
        philly.assign(source="opendataphilly")[["organization_id", "source", "source_objectids",
                                                 "service_types", "lat", "lon"]],
        syn.assign(source="synthetic")[["organization_id", "source"]]], ignore_index=True)

    log(f"\n**Organization table: {len(org)} rows** = {len(philly)} real Philadelphia sites "
        f"(ids 1-{len(philly)}) + {len(syn)} synthetic organisations "
        f"(ids {len(philly)+1}-{len(org)}).\n")
    log(org.organization_type.value_counts().to_frame("rows").to_markdown() + "\n")
    return org, keys, meta


def build_categories():
    cat = pd.read_csv(SYN_RAW_DIR / "food_categories.csv")
    cat.insert(0, "category_id", np.arange(1, len(cat) + 1))
    return cat


def clean_activity(raw: pd.DataFrame, kind: str, keys: pd.DataFrame, org: pd.DataFrame,
                   cat: pd.DataFrame) -> pd.DataFrame:
    if kind == "donation":
        key_col, qty_col, t0, ts = "donor_key", "quantity", "donated_at", ["donated_at", "expires_at", "pickup_deadline"]
        roles, org_col, ref = {"donor", "both"}, "donor_org_id", "don_ref"
    else:
        key_col, qty_col, t0, ts = "recipient_key", "requested_quantity", "requested_at", ["requested_at", "needed_by"]
        roles, org_col, ref = {"recipient", "both"}, "recipient_org_id", "req_ref"

    df = raw.copy()
    steps = [("raw rows", len(df))]

    df[org_col] = df[key_col].map(keys.set_index("raw_key").organization_id)
    df = df[df[org_col].notna()]
    steps.append(("unknown organisation key removed", len(df)))
    df[org_col] = df[org_col].astype(int)
    df = df[df[org_col].map(org.set_index("organization_id").organization_type).isin(roles)]
    steps.append((f"organisation not a valid {'donor' if kind == 'donation' else 'recipient'} removed", len(df)))

    cmap = {cat_key(n): i for n, i in zip(cat.category_name, cat.category_id)}
    df["category_id"] = df.category_label.map(lambda l: cmap.get(cat_key(l)))
    n_fixed = (df.category_label.isin(cat.category_name) == False).sum()  # noqa: E712
    df = df[df.category_id.notna()]
    steps.append((f"unmapped category label removed ({n_fixed} variant labels standardised)", len(df)))
    df["category_id"] = df.category_id.astype(int)

    q = df[qty_col].map(parse_qty)
    n_text = df[qty_col].astype(str).str.contains("[a-z]", case=False, na=False).sum()
    df[qty_col] = q
    df = df[df[qty_col].notna() & (df[qty_col] > 0)]
    steps.append((f"missing / non-positive quantity removed ({n_text} '45 servings'-style values parsed)", len(df)))
    df[qty_col] = df[qty_col].astype(int)

    n_us = df[t0].astype(str).str.contains("/").sum()
    for c in ts:
        df[c] = parse_ts(df[c])
    df = df.dropna(subset=ts)
    steps.append((f"unparseable timestamp removed ({n_us} MM/DD/YYYY timestamps converted)", len(df)))

    if kind == "donation":
        df = df[(df.expires_at > df.donated_at) & (df.pickup_deadline >= df.donated_at)]
        steps.append(("expiry before posting / pickup before posting removed", len(df)))
        late = df.pickup_deadline > df.expires_at
        df.loc[late, "pickup_deadline"] = df.loc[late, "expires_at"]
        steps.append((f"pickup deadline clamped to expiry ({late.sum()} rows)", len(df)))
        dkey = [org_col, "category_id", qty_col, "donated_at", "expires_at"]
    else:
        df = df[df.needed_by >= df.requested_at]
        steps.append(("needed-by before request time removed", len(df)))
        dkey = [org_col, "category_id", qty_col, "requested_at", "needed_by"]

    # double submissions: identical record under a new reference (possibly
    # via a duplicate registration, which only becomes visible after ER)
    # (compared at minute precision: the MM/DD/YYYY export format drops seconds)
    minute = {c: df[c].dt.floor("min") for c in dkey if c in ts}
    df = df.loc[df.assign(**minute).sort_values(ref).drop_duplicates(subset=dkey, keep="first").index]
    steps.append(("duplicate submissions removed (same org, category, quantity, timestamps)", len(df)))

    df = df.sort_values([t0, ref]).reset_index(drop=True)
    id_col = "donation_id" if kind == "donation" else "request_id"
    df.insert(0, id_col, np.arange(1, len(df) + 1))

    log(f"\n## {'2' if kind == 'donation' else '3'}. "
        f"{'FoodDonation' if kind == 'donation' else 'RecipientRequest'} cleaning\n")
    t = pd.DataFrame(steps, columns=["step", "rows remaining"])
    t["removed"] = (-t["rows remaining"].diff()).fillna(0).astype(int)
    log(t.to_markdown(index=False))
    keep = [id_col, org_col, "category_id", qty_col] + ts + [ref]
    return df[keep]


def main():
    org, keys, meta = build_organizations()
    cat = build_categories()
    don = clean_activity(pd.read_csv(SYN_RAW_DIR / "donations_raw.csv", dtype=str), "donation", keys, org, cat)
    req = clean_activity(pd.read_csv(SYN_RAW_DIR / "requests_raw.csv", dtype=str), "request", keys, org, cat)

    org.to_csv(INTERIM_DIR / "organization.csv", index=False)
    meta.to_csv(INTERIM_DIR / "organization_meta.csv", index=False)
    keys.to_csv(INTERIM_DIR / "org_key_map.csv", index=False)
    cat.to_csv(INTERIM_DIR / "food_category.csv", index=False)
    don.to_csv(INTERIM_DIR / "donation_clean.csv", index=False)
    req.to_csv(INTERIM_DIR / "request_clean.csv", index=False)
    (REPORT_DIR / "cleaning_report.md").write_text(
        "# Synthetic data cleaning & integration report\n\n" + "\n".join(LOG), encoding="utf-8")
    print(f"organizations {len(org)} | categories {len(cat)} | donations {len(don)} | requests {len(req)}")


if __name__ == "__main__":
    main()
