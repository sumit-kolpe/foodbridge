-- FoodBridge - post-load verification (run in DataGrip after loading)
-- Expected: Organization 1000, FoodCategory 25, FoodDonation 150000,
--           RecipientRequest 120000, Allocation 198415; every check = 0.

-- 1. Row counts
SELECT 'Organization' AS table_name, COUNT(*) AS row_count FROM Organization
UNION ALL SELECT 'FoodCategory', COUNT(*) FROM FoodCategory
UNION ALL SELECT 'FoodDonation', COUNT(*) FROM FoodDonation
UNION ALL SELECT 'RecipientRequest', COUNT(*) FROM RecipientRequest
UNION ALL SELECT 'Allocation', COUNT(*) FROM Allocation;

-- 2. Business-rule checks (FKs and CHECKs are already enforced by the DDL)
SELECT 'donations over-allocated' AS check_name, COUNT(*) AS violations FROM (
    SELECT d.donation_id FROM FoodDonation d JOIN Allocation a ON a.donation_id = d.donation_id
    WHERE a.status <> 'cancelled' GROUP BY d.donation_id, d.quantity
    HAVING SUM(a.quantity_allocated) > d.quantity) x
UNION ALL
SELECT 'requests over-allocated', COUNT(*) FROM (
    SELECT r.request_id FROM RecipientRequest r JOIN Allocation a ON a.request_id = r.request_id
    WHERE a.status <> 'cancelled' GROUP BY r.request_id, r.requested_quantity
    HAVING SUM(a.quantity_allocated) > r.requested_quantity) y
UNION ALL
SELECT 'category mismatch', COUNT(*) FROM Allocation a
    JOIN FoodDonation d ON d.donation_id = a.donation_id
    JOIN RecipientRequest r ON r.request_id = a.request_id
    WHERE d.category_id <> r.category_id
UNION ALL
SELECT 'NULL timestamps loaded as empty', COUNT(*) FROM Allocation
    WHERE status = 'delivered' AND (delivered_at IS NULL OR picked_up_at IS NULL);

-- 3. Make SERIAL sequences continue after the loaded ids
--    (needed if you imported with DataGrip; load_data.sql already does this)
SELECT setval(pg_get_serial_sequence('organization', 'organization_id'), (SELECT MAX(organization_id) FROM Organization));
SELECT setval(pg_get_serial_sequence('foodcategory', 'category_id'), (SELECT MAX(category_id) FROM FoodCategory));
SELECT setval(pg_get_serial_sequence('fooddonation', 'donation_id'), (SELECT MAX(donation_id) FROM FoodDonation));
SELECT setval(pg_get_serial_sequence('recipientrequest', 'request_id'), (SELECT MAX(request_id) FROM RecipientRequest));
SELECT setval(pg_get_serial_sequence('allocation', 'allocation_id'), (SELECT MAX(allocation_id) FROM Allocation));

-- 4. Refresh planner statistics
ANALYZE;
