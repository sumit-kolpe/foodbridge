"""06_make_insert_scripts.py - Write each processed CSV as batched INSERT statements
(sql/inserts/) for clients without psql \\copy, e.g. DataGrip.
Usage: python scripts/06_make_insert_scripts.py ."""
import csv, sys
from pathlib import Path
root = Path(sys.argv[1])
src, out = root / "data" / "processed", root / "sql" / "inserts"
out.mkdir(parents=True, exist_ok=True)
tables = [("organization.csv", "Organization", {"organization_id"}),
          ("food_category.csv", "FoodCategory", {"category_id"}),
          ("food_donation.csv", "FoodDonation", {"donation_id", "donor_org_id", "category_id", "quantity"}),
          ("recipient_request.csv", "RecipientRequest", {"request_id", "recipient_org_id", "category_id", "requested_quantity"}),
          ("allocation.csv", "Allocation", {"allocation_id", "donation_id", "request_id", "quantity_allocated"})]
def lit(v, numeric):
    if v == "": return "NULL"
    return v if numeric else "'" + v.replace("'", "''") + "'"
(out / "00_reset_tables.sql").write_text(
    "-- Empties all tables (safe to re-run the inserts afterwards)\n"
    "TRUNCATE Allocation, RecipientRequest, FoodDonation, FoodCategory, Organization;\n")
for n, (f, t, nums) in enumerate(tables, 1):
    with open(src / f, newline="", encoding="utf-8") as fh, \
         open(out / f"{n:02d}_{f.replace('.csv', '.sql')}", "w", encoding="utf-8") as w:
        r = csv.reader(fh); cols = next(r)
        w.write(f"-- {t}: generated from data/processed/{f}\n")
        batch = []
        def flush():
            w.write(f"INSERT INTO {t} ({', '.join(cols)}) VALUES\n" + ",\n".join(batch) + ";\n")
            batch.clear()
        for row in r:
            batch.append("(" + ", ".join(lit(v, c in nums) for v, c in zip(row, cols)) + ")")
            if len(batch) == 1000: flush()
        if batch: flush()
(out / "06_finish.sql").write_text(
    "-- Move SERIAL sequences past the loaded ids, refresh statistics\n"
    "SELECT setval(pg_get_serial_sequence('organization', 'organization_id'), (SELECT MAX(organization_id) FROM Organization));\n"
    "SELECT setval(pg_get_serial_sequence('foodcategory', 'category_id'), (SELECT MAX(category_id) FROM FoodCategory));\n"
    "SELECT setval(pg_get_serial_sequence('fooddonation', 'donation_id'), (SELECT MAX(donation_id) FROM FoodDonation));\n"
    "SELECT setval(pg_get_serial_sequence('recipientrequest', 'request_id'), (SELECT MAX(request_id) FROM RecipientRequest));\n"
    "SELECT setval(pg_get_serial_sequence('allocation', 'allocation_id'), (SELECT MAX(allocation_id) FROM Allocation));\n"
    "ANALYZE;\n")
for p in sorted(out.iterdir()): print(p.name, round(p.stat().st_size/1e6, 1), "MB")
