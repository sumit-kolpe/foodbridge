"""
01_clean_philly_sites.py - EDA, cleaning and entity resolution for the
City of Philadelphia "Free Food and Meal Sites" dataset.

Input : data/raw/philly_free_food_sites_raw_2026-11-10.csv
        (frozen export of the ArcGIS FeatureServer layer `free_meal_sites`,
         downloaded 2026-11-10, 404 rows x 53 columns incl. lon/lat)
Output: data/interim/philly_sites_clean.csv     one row per resolved organisation
        data/interim/philly_er_map.csv          raw objectid -> resolved cluster
        reports/philly_eda.md                   EDA + cleaning log

Cleaning steps
  1. Trim whitespace/newlines in every text field.
  2. Standardise ZIP codes to 5 digits; standardise status (Active ->
     active, Permanently Closed -> inactive).
  3. Split the free-text phone_number field into a normalised phone and email.
  4. Entity resolution: the city lists one row per *program* (e.g. a church
     that is both a Philabundance food site and an OHS meal site appears
     twice, often with "Ave" vs "Ave." differences). Rows at the same
     normalised address with similar names are merged into one organisation.
  5. Resolve conflicting attributes inside a cluster (status, ZIP, contact).
  6. Filter by purpose: clusters that only offer "Public Benefits" (WIC,
     BenePhilly...) do not receive food and are removed.
"""

import pandas as pd

from common import (CITY, INTERIM_DIR, PHILLY_RAW, REPORT_DIR, clean_text,
                    contact_string, norm_address, norm_status, norm_zip,
                    parse_contact, resolve_entities)

FOOD_TYPES = {"Food Site", "General Meal Site", "Senior Meal Site"}


def main():
    raw = pd.read_csv(PHILLY_RAW, dtype=str)
    log = [f"# Philadelphia Free Food & Meal Sites - EDA and cleaning log\n",
           f"Source: City of Philadelphia ArcGIS layer `free_meal_sites` "
           f"(OpenDataPhilly), exported 2026-11-10.\n",
           f"* Raw file size: {PHILLY_RAW.stat().st_size/1024:.1f} KB",
           f"* Raw shape: {raw.shape[0]} rows x {raw.shape[1]} columns "
           f"(51 source attributes + exported lon/lat)\n"]

    # ---------------- EDA ----------------
    log.append("## Categorical distributions (raw)\n")
    for col in ["category_type", "status", "category"]:
        vc = raw[col].value_counts(dropna=False)
        log.append(f"**{col}**\n\n" + vc.to_frame("rows").to_markdown() + "\n")
    miss = raw.isna().mean().mul(100).round(1)
    log.append("## Missing values (% of rows) for key fields\n")
    key = ["site_name", "address", "zip_code", "phone_number", "website",
           "hours_mon_start1", "site_key", "email"]
    log.append(miss[key].to_frame("% missing").to_markdown() + "\n")
    hours_cols = [c for c in raw.columns if c.startswith("hours_")]
    no_hours = raw[hours_cols].isna().all(axis=1).sum()
    log.append(f"* Rows with **no** operating hours at all: {no_hours} "
               f"({no_hours/len(raw):.1%}). Treated as *unknown*, not closed.")
    ll = raw[["lat", "lon"]].astype(float)
    log.append(f"* Latitude {ll.lat.min():.3f} to {ll.lat.max():.3f} "
               f"(mean {ll.lat.mean():.4f}, sd {ll.lat.std():.4f}); "
               f"longitude {ll.lon.min():.3f} to {ll.lon.max():.3f} "
               f"(mean {ll.lon.mean():.4f}, sd {ll.lon.std():.4f})\n")

    # ---------------- 1-3. field cleaning ----------------
    df = raw.copy()
    for c in df.columns:
        df[c] = df[c].map(clean_text)
    df["objectid"] = df["objectid"].astype(int)
    df["zip5"] = df["zip_code"].map(norm_zip)
    # fall back to a ZIP embedded in the address text, if any
    df.loc[df.zip5.isna(), "zip5"] = df.loc[df.zip5.isna(), "address"].map(norm_zip)
    df["status_std"] = df["status"].map(norm_status)
    pe = df["phone_number"].map(parse_contact)
    df["phone"] = pe.str[0]
    df["email_std"] = pe.str[1].fillna(df["email"].map(lambda e: parse_contact(e)[1]))
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)
    df["addr_key"] = df["address"].map(norm_address)

    n_missing_zip = df.zip5.isna().sum()
    log.append("## Cleaning log\n")
    log.append(f"* ZIP codes standardised to 5 digits; {n_missing_zip} row(s) "
               f"have no recoverable ZIP and keep NULL (not imputed).")
    log.append(f"* Status mapped: {df.status_std.value_counts().to_dict()}")
    log.append(f"* Contact field split: {df.phone.notna().sum()} phones and "
               f"{df.email_std.notna().sum()} emails extracted "
               f"(emails were mixed into `phone_number` in the source).")

    # ---------------- 4. entity resolution ----------------
    df["cluster"] = resolve_entities(df, "objectid", "site_name", "address")
    sizes = df.groupby("cluster").size()
    merged = sizes[sizes > 1]
    log.append(f"* Entity resolution (block = normalised address, match = "
               f"name similarity >= 0.6): {len(df)} rows -> {len(sizes)} "
               f"organisations; {len(merged)} clusters merged "
               f"{merged.sum()} rows.\n")
    log.append("### Merged clusters\n")
    rows = []
    for cid in merged.index:
        g = df[df.cluster == cid]
        rows.append({"cluster": cid,
                     "names": " | ".join(g.site_name.unique()),
                     "addresses": " | ".join(g.address.unique()),
                     "types": ", ".join(sorted(g.category_type.unique()))})
    log.append(pd.DataFrame(rows).to_markdown(index=False) + "\n")

    # ---------------- 5. cluster -> one organisation ----------------
    # centroid of each ZIP, used to settle ZIP conflicts inside a cluster
    zc = df.dropna(subset=["zip5"]).groupby("zip5")[["lat", "lon"]].mean()

    MARKET_ST_LAT = 39.9524   # Philadelphia N/S house numbering starts at Market St

    def geo_consistent(row) -> bool:
        """An 'N ...' address must geocode north of Market St, 'S ...' south."""
        key = norm_address(row.address).split()
        if len(key) > 1 and key[1] in ("n", "s"):
            return (row.lat > MARKET_ST_LAT) == (key[1] == "n")
        return True

    def pick_zip(g):
        """Resolve the ZIP of a cluster. On conflict, discard records whose
        geocode contradicts the street direction, then take the ZIP whose
        centroid is nearest to the remaining records' coordinates."""
        zips = g.zip5.dropna().unique()
        if len(zips) <= 1:
            return (zips[0] if len(zips) else None), g
        ok = g[g.apply(geo_consistent, axis=1)]
        g = ok if len(ok) else g
        zips = g.zip5.dropna().unique()
        lat, lon = g.lat.mean(), g.lon.mean()
        d = ((zc.loc[zips, "lat"] - lat) ** 2 + (zc.loc[zips, "lon"] - lon) ** 2)
        return d.idxmin(), g

    orgs = []
    conflicts = []
    for cid, g in df.groupby("cluster"):
        # canonical row: active first, then has phone, then longest name
        g = g.assign(_a=(g.status_std == "active").astype(int),
                     _p=g.phone.notna().astype(int),
                     _l=g.site_name.str.len())
        best = g.sort_values(["_a", "_p", "_l", "objectid"],
                             ascending=[False, False, False, True]).iloc[0]
        z, geo = pick_zip(g)
        if g.zip5.nunique() > 1:
            conflicts.append(f"{best.site_name} ({best.address}): "
                             f"{sorted(g.zip5.dropna().unique())} -> {z} "
                             f"(record geocoded on the wrong side of Market St discarded)")
        types = set(g.category_type)
        orgs.append({
            "source_cluster_id": cid,
            "source_objectids": ";".join(map(str, sorted(g.objectid))),
            "organization_name": best.site_name,
            "address": best.address,
            "city": CITY,
            "zip_code": z,
            "contact_information": contact_string(
                g.phone.dropna().iloc[0] if g.phone.notna().any() else None,
                g.email_std.dropna().iloc[0] if g.email_std.notna().any() else None),
            # one active program is enough for the site to be active
            "status": "active" if (g.status_std == "active").any() else "inactive",
            "service_types": ";".join(sorted(types)),
            "is_food_recipient": bool(types & FOOD_TYPES),
            "lat": round(geo.lat.mean(), 6),
            "lon": round(geo.lon.mean(), 6),
            "has_hours": bool(g[hours_cols].notna().any(axis=1).any()),
        })
    orgs = pd.DataFrame(orgs)
    log.append("### ZIP conflicts resolved (nearest ZIP centroid to site coordinates)\n")
    log.extend(f"* {c}" for c in conflicts) if conflicts else log.append("* none")

    # ---------------- 6. filter by purpose ----------------
    removed = orgs[~orgs.is_food_recipient]
    orgs = orgs[orgs.is_food_recipient].drop(columns="is_food_recipient")
    log.append(f"\n* Removed {len(removed)} public-benefits-only organisations "
               f"(they do not receive food donations).")
    log.append(f"* **Final: {len(orgs)} recipient organisations** "
               f"({(orgs.status=='active').sum()} active, "
               f"{(orgs.status=='inactive').sum()} inactive).")
    log.append("\nFinal service-type mix:\n")
    log.append(orgs.service_types.value_counts().to_frame("orgs").to_markdown())

    orgs.to_csv(INTERIM_DIR / "philly_sites_clean.csv", index=False)
    df[["objectid", "site_name", "address", "cluster"]].to_csv(
        INTERIM_DIR / "philly_er_map.csv", index=False)
    (REPORT_DIR / "philly_eda.md").write_text("\n".join(log), encoding="utf-8")
    print(f"raw {len(raw)} -> resolved {len(sizes)} -> recipients {len(orgs)}")


if __name__ == "__main__":
    main()
