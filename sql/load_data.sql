-- FoodBridge - bulk load of the processed CSVs (run from the repo root)
--   psql -h <rds-endpoint> -U <user> -d <db> -f sql/load_data.sql
-- \copy reads the files on YOUR machine and streams them to the server,
-- so it works with AWS RDS (no superuser / server file access needed).
-- Order follows the foreign-key dependencies.

\echo 'Loading Organization...'
\copy Organization (organization_id, organization_name, organization_type, address, city, zip_code, contact_information, status) FROM 'data/processed/organization.csv' WITH (FORMAT csv, HEADER true)

\echo 'Loading FoodCategory...'
\copy FoodCategory (category_id, category_name, storage_type, description) FROM 'data/processed/food_category.csv' WITH (FORMAT csv, HEADER true)

\echo 'Loading FoodDonation...'
\copy FoodDonation (donation_id, donor_org_id, category_id, quantity, donated_at, expires_at, pickup_deadline, status) FROM 'data/processed/food_donation.csv' WITH (FORMAT csv, HEADER true)

\echo 'Loading RecipientRequest...'
\copy RecipientRequest (request_id, recipient_org_id, category_id, requested_quantity, requested_at, needed_by, status) FROM 'data/processed/recipient_request.csv' WITH (FORMAT csv, HEADER true)

\echo 'Loading Allocation...'
\copy Allocation (allocation_id, donation_id, request_id, quantity_allocated, allocated_at, status, picked_up_at, delivered_at) FROM 'data/processed/allocation.csv' WITH (FORMAT csv, HEADER true)

-- explicit ids were loaded, so move each SERIAL sequence past the max id
SELECT setval(pg_get_serial_sequence('organization', 'organization_id'), (SELECT MAX(organization_id) FROM Organization));
SELECT setval(pg_get_serial_sequence('foodcategory', 'category_id'), (SELECT MAX(category_id) FROM FoodCategory));
SELECT setval(pg_get_serial_sequence('fooddonation', 'donation_id'), (SELECT MAX(donation_id) FROM FoodDonation));
SELECT setval(pg_get_serial_sequence('recipientrequest', 'request_id'), (SELECT MAX(request_id) FROM RecipientRequest));
SELECT setval(pg_get_serial_sequence('allocation', 'allocation_id'), (SELECT MAX(allocation_id) FROM Allocation));

ANALYZE;

-- row-count check
SELECT 'Organization' AS table_name, COUNT(*) AS row_count FROM Organization
UNION ALL SELECT 'FoodCategory', COUNT(*) FROM FoodCategory
UNION ALL SELECT 'FoodDonation', COUNT(*) FROM FoodDonation
UNION ALL SELECT 'RecipientRequest', COUNT(*) FROM RecipientRequest
UNION ALL SELECT 'Allocation', COUNT(*) FROM Allocation;
