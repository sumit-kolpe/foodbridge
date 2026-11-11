"""
05_validate_and_summarize.py - Verify the final CSVs against the SQL DDL
constraints and the FoodBridge business rules, then write summary statistics.

Fails (exit code 1) if any check is violated, so it can gate the DB load.
Output: reports/data_summary.md
"""

import sys

import pandas as pd

from common import AS_OF, FINAL_DIR, REPORT_DIR

checks: list[tuple[str, int]] = []


def check(name, bad):
    n = int(bad.sum()) if hasattr(bad, "sum") else int(bad)
    checks.append((name, n))


def main():
    org = pd.read_csv(FINAL_DIR / "organization.csv", dtype={"zip_code": str})
    cat = pd.read_csv(FINAL_DIR / "food_category.csv")
    d = pd.read_csv(FINAL_DIR / "food_donation.csv",
                    parse_dates=["donated_at", "expires_at", "pickup_deadline"])
    r = pd.read_csv(FINAL_DIR / "recipient_request.csv", parse_dates=["requested_at", "needed_by"])
    a = pd.read_csv(FINAL_DIR / "allocation.csv",
                    parse_dates=["allocated_at", "picked_up_at", "delivered_at"])

    # ---------------- primary keys ----------------
    for name, df, pk in [("Organization", org, "organization_id"), ("FoodCategory", cat, "category_id"),
                         ("FoodDonation", d, "donation_id"), ("RecipientRequest", r, "request_id"),
                         ("Allocation", a, "allocation_id")]:
        check(f"{name}: PK unique & not null", df[pk].duplicated() | df[pk].isna())
    check("FoodCategory: category_name unique", cat.category_name.duplicated())

    # ---------------- NOT NULL / CHECK constraints ----------------
    check("Organization: name not null", org.organization_name.isna())
    check("Organization: type in (donor,recipient,both)", ~org.organization_type.isin(["donor", "recipient", "both"]))
    check("Organization: status in (active,inactive)", ~org.status.isin(["active", "inactive"]))
    check("Organization: name <= 150 chars", org.organization_name.str.len() > 150)
    check("Organization: contact <= 100 chars", org.contact_information.str.len() > 100)
    check("Organization: zip <= 15 chars", org.zip_code.str.len() > 15)
    check("FoodCategory: storage_type valid", ~cat.storage_type.isin(["refrigerated", "frozen", "shelf-stable", "other"]))
    check("FoodDonation: quantity > 0", d.quantity <= 0)
    check("FoodDonation: expires_at > donated_at", d.expires_at <= d.donated_at)
    check("FoodDonation: pickup_deadline >= donated_at", d.pickup_deadline < d.donated_at)
    check("FoodDonation: status valid", ~d.status.isin(["available", "partially_allocated", "fully_allocated",
                                                        "expired", "cancelled"]))
    check("RecipientRequest: requested_quantity > 0", r.requested_quantity <= 0)
    check("RecipientRequest: needed_by >= requested_at", r.needed_by < r.requested_at)
    check("RecipientRequest: status valid", ~r.status.isin(["open", "partially_fulfilled", "fulfilled",
                                                            "expired", "cancelled"]))
    check("Allocation: quantity_allocated > 0", a.quantity_allocated <= 0)
    check("Allocation: status valid", ~a.status.isin(["pending", "confirmed", "picked_up", "delivered", "cancelled"]))
    check("Allocation: delivered_at implies picked_up_at", a.delivered_at.notna() & a.picked_up_at.isna())

    # ---------------- foreign keys ----------------
    check("FK FoodDonation.donor_org_id", ~d.donor_org_id.isin(org.organization_id))
    check("FK FoodDonation.category_id", ~d.category_id.isin(cat.category_id))
    check("FK RecipientRequest.recipient_org_id", ~r.recipient_org_id.isin(org.organization_id))
    check("FK RecipientRequest.category_id", ~r.category_id.isin(cat.category_id))
    check("FK Allocation.donation_id", ~a.donation_id.isin(d.donation_id))
    check("FK Allocation.request_id", ~a.request_id.isin(r.request_id))

    # ---------------- business rules ----------------
    otype = org.set_index("organization_id").organization_type
    check("Donor org is donor/both", ~d.donor_org_id.map(otype).isin(["donor", "both"]))
    check("Recipient org is recipient/both", ~r.recipient_org_id.map(otype).isin(["recipient", "both"]))
    ad = a.merge(d, on="donation_id", suffixes=("", "_d")).merge(r, on="request_id", suffixes=("", "_r"))
    act = ad[ad.status != "cancelled"]
    s = act.groupby("donation_id").quantity_allocated.sum()
    check("Active allocations <= donation quantity", s > d.set_index("donation_id").quantity[s.index])
    s = act.groupby("request_id").quantity_allocated.sum()
    check("Active allocations <= requested quantity", s > r.set_index("request_id").requested_quantity[s.index])
    check("Allocation category: donation = request", ad.category_id != ad.category_id_r)
    check("allocated_at >= donated_at and >= requested_at",
          (ad.allocated_at < ad.donated_at) | (ad.allocated_at < ad.requested_at))
    check("allocated_at <= pickup_deadline and <= needed_by",
          (ad.allocated_at > ad.pickup_deadline) | (ad.allocated_at > ad.needed_by))
    check("picked_up_at in [allocated_at, pickup_deadline]",
          ad.picked_up_at.notna() & ((ad.picked_up_at < ad.allocated_at) | (ad.picked_up_at > ad.pickup_deadline)))
    check("delivered_at > picked_up_at", ad.delivered_at.notna() & (ad.delivered_at <= ad.picked_up_at))
    check("Delivered rows have both timestamps",
          (ad.status == "delivered") & (ad.delivered_at.isna() | ad.picked_up_at.isna()))
    check("No event after snapshot time",
          (d.donated_at > AS_OF).sum() + (r.requested_at > AS_OF).sum() + (a.allocated_at > AS_OF).sum()
          + (a.delivered_at > AS_OF).sum())
    check("Cancelled donations/requests have no allocations",
          a.donation_id.isin(d.donation_id[d.status == "cancelled"]).sum()
          + a.request_id.isin(r.request_id[r.status == "cancelled"]).sum())

    failed = [c for c in checks if c[1]]

    # ---------------- summary statistics ----------------
    def size(f):
        return (FINAL_DIR / f).stat().st_size / 1e6

    files = [("Organization", "organization.csv", org), ("FoodCategory", "food_category.csv", cat),
             ("FoodDonation", "food_donation.csv", d), ("RecipientRequest", "recipient_request.csv", r),
             ("Allocation", "allocation.csv", a)]
    out = ["# FoodBridge - final dataset summary\n",
           f"Snapshot time (AS_OF): {AS_OF}. Activity window: {d.donated_at.min():%Y-%m-%d} "
           f"to {d.donated_at.max():%Y-%m-%d %H:%M}.\n", "## Table sizes\n"]
    out.append(pd.DataFrame([{"table": t, "rows": len(df), "attributes": df.shape[1],
                              "csv size (MB)": round(size(f), 2)} for t, f, df in files]).to_markdown(index=False))
    out.append(f"\n**Total rows: {sum(len(x[2]) for x in files):,}**\n")

    def stats(sr, label):
        return {"attribute": label, "n": len(sr), "mean": round(sr.mean(), 2), "median": sr.median(),
                "std": round(sr.std(), 2), "min": sr.min(), "max": sr.max()}
    out.append("## Numeric attributes (servings)\n")
    out.append(pd.DataFrame([stats(d.quantity, "FoodDonation.quantity"),
                             stats(r.requested_quantity, "RecipientRequest.requested_quantity"),
                             stats(a.quantity_allocated, "Allocation.quantity_allocated")]).to_markdown(index=False))
    life = (d.expires_at - d.donated_at).dt.total_seconds() / 86400
    win = (d.pickup_deadline - d.donated_at).dt.total_seconds() / 3600
    lead = (r.needed_by - r.requested_at).dt.total_seconds() / 86400
    out.append("\n" + pd.DataFrame([stats(life, "shelf life (days)"), stats(win, "pickup window (hours)"),
                                    stats(lead, "request lead time (days)")]).round(2).to_markdown(index=False))

    out.append("\n## Status distributions\n")
    for t, df in [("FoodDonation", d), ("RecipientRequest", r), ("Allocation", a)]:
        vc = df.status.value_counts()
        out.append(f"**{t}**\n\n" + pd.DataFrame({"rows": vc, "%": (vc / len(df) * 100).round(1)}).to_markdown() + "\n")
    out.append("**Organization**\n\n" + org.groupby(["organization_type", "status"]).size()
               .to_frame("rows").to_markdown() + "\n")

    delivered = a[a.status == "delivered"].quantity_allocated.sum()
    active = a[a.status != "cancelled"].quantity_allocated.sum()
    exp = d[d.status == "expired"]
    exp_left = exp.quantity.sum() - act[act.donation_id.isin(exp.donation_id)].quantity_allocated.sum()
    out.append("## Redistribution overview\n")
    out.append(pd.DataFrame([
        ("servings donated", d.quantity.sum()), ("servings requested", r.requested_quantity.sum()),
        ("servings allocated (non-cancelled)", active), ("servings delivered", delivered),
        ("% of donated servings delivered", round(delivered / d.quantity.sum() * 100, 1)),
        ("% of requested servings delivered", round(delivered / r.requested_quantity.sum() * 100, 1)),
        ("servings lost in expired donations", exp_left),
        ("donations never allocated", int((~d.donation_id.isin(act.donation_id)).sum())),
        ("allocations per donation (allocated ones)", round(len(act) / act.donation_id.nunique(), 2)),
    ], columns=["metric", "value"]).assign(value=lambda x: x.value.map(lambda v: f"{v:,.0f}" if float(v) > 100 else f"{v}"))
        .to_markdown(index=False, colalign=("left", "right"), disable_numparse=True))

    cn = cat.set_index("category_id").category_name
    by_cat = pd.DataFrame({"donated": d.groupby("category_id").quantity.sum(),
                           "requested": r.groupby("category_id").requested_quantity.sum(),
                           "delivered": a[a.status == "delivered"].merge(d[["donation_id", "category_id"]])
                           .groupby("category_id").quantity_allocated.sum()}).fillna(0).astype(int)
    by_cat.index = by_cat.index.map(cn)
    by_cat["fill rate %"] = (by_cat.delivered / by_cat.requested * 100).round(1)
    out.append("\n## By food category (servings)\n")
    out.append(by_cat.sort_values("requested", ascending=False).to_markdown(intfmt=","))

    month = pd.DataFrame({"donations": d.groupby(d.donated_at.dt.to_period("M")).size(),
                          "requests": r.groupby(r.requested_at.dt.to_period("M")).size(),
                          "allocations": a.groupby(a.allocated_at.dt.to_period("M")).size()})
    out.append("\n## Monthly volume (rows)\n")
    out.append(month.to_markdown())

    out.append("\n## Validation checks\n")
    out.append(pd.DataFrame(checks, columns=["check", "violations"]).to_markdown(index=False))
    (REPORT_DIR / "data_summary.md").write_text("\n".join(out), encoding="utf-8")

    print(f"{len(checks)} checks, {len(failed)} failed")
    for c in failed:
        print("FAILED:", c)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
