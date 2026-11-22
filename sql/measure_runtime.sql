-- =============================================================================
-- FoodBridge - baseline runtimes of the long-running queries Q10 and Q12 on RDS
-- (Milestone 3 feedback). Run as the master user in DataGrip, connected to the
-- foodbridge database, BEFORE adding any index.
--
-- How to run: execute each statement separately (cursor inside it, Ctrl+Enter).
-- Each EXPLAIN ANALYZE really executes the query and prints its plan; the last
-- line of the output is "Execution Time: ... ms". Record that number.
-- Run 1 is "cold" (data not cached yet); runs 2-3 are "warm".
-- Expect roughly 1-5 minutes per run on a small RDS instance.
-- =============================================================================

-- 0. Context for the report
SELECT version();
SET statement_timeout = 0;            -- no time limit for this session
-- Only the primary-key indexes should be listed here (5 rows):
SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1, 2;

-- Q10 Avoidable food loss - run 1
EXPLAIN (ANALYZE, BUFFERS)
WITH expired_leftover AS (
    SELECT d.donation_id, d.donor_org_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE((SELECT SUM(a.quantity_allocated)
                                  FROM Allocation a
                                  WHERE a.donation_id = d.donation_id
                                    AND a.status <> 'cancelled'), 0) AS leftover
    FROM FoodDonation d
    WHERE d.status = 'expired'
      AND d.donated_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
)
SELECT c.category_name, o.organization_name AS donor,
       COUNT(*)        AS avoidable_expired_donations,
       SUM(e.leftover) AS avoidable_lost_servings
FROM expired_leftover e
JOIN FoodCategory c ON c.category_id = e.category_id
JOIN Organization o ON o.organization_id = e.donor_org_id
WHERE e.leftover > 0
  AND EXISTS (
        SELECT 1
        FROM RecipientRequest r
        WHERE r.category_id = e.category_id
          AND r.status <> 'cancelled'
          AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
          AND r.requested_at <= e.pickup_deadline
          AND r.needed_by    >= e.donated_at
          AND r.requested_quantity > COALESCE((SELECT SUM(a2.quantity_allocated)
                                               FROM Allocation a2
                                               WHERE a2.request_id = r.request_id
                                                 AND a2.status <> 'cancelled'), 0))
GROUP BY c.category_name, o.organization_name
ORDER BY avoidable_lost_servings DESC
LIMIT 25;

-- Q10 Avoidable food loss - run 2
EXPLAIN (ANALYZE, BUFFERS)
WITH expired_leftover AS (
    SELECT d.donation_id, d.donor_org_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE((SELECT SUM(a.quantity_allocated)
                                  FROM Allocation a
                                  WHERE a.donation_id = d.donation_id
                                    AND a.status <> 'cancelled'), 0) AS leftover
    FROM FoodDonation d
    WHERE d.status = 'expired'
      AND d.donated_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
)
SELECT c.category_name, o.organization_name AS donor,
       COUNT(*)        AS avoidable_expired_donations,
       SUM(e.leftover) AS avoidable_lost_servings
FROM expired_leftover e
JOIN FoodCategory c ON c.category_id = e.category_id
JOIN Organization o ON o.organization_id = e.donor_org_id
WHERE e.leftover > 0
  AND EXISTS (
        SELECT 1
        FROM RecipientRequest r
        WHERE r.category_id = e.category_id
          AND r.status <> 'cancelled'
          AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
          AND r.requested_at <= e.pickup_deadline
          AND r.needed_by    >= e.donated_at
          AND r.requested_quantity > COALESCE((SELECT SUM(a2.quantity_allocated)
                                               FROM Allocation a2
                                               WHERE a2.request_id = r.request_id
                                                 AND a2.status <> 'cancelled'), 0))
GROUP BY c.category_name, o.organization_name
ORDER BY avoidable_lost_servings DESC
LIMIT 25;

-- Q10 Avoidable food loss - run 3
EXPLAIN (ANALYZE, BUFFERS)
WITH expired_leftover AS (
    SELECT d.donation_id, d.donor_org_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE((SELECT SUM(a.quantity_allocated)
                                  FROM Allocation a
                                  WHERE a.donation_id = d.donation_id
                                    AND a.status <> 'cancelled'), 0) AS leftover
    FROM FoodDonation d
    WHERE d.status = 'expired'
      AND d.donated_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
)
SELECT c.category_name, o.organization_name AS donor,
       COUNT(*)        AS avoidable_expired_donations,
       SUM(e.leftover) AS avoidable_lost_servings
FROM expired_leftover e
JOIN FoodCategory c ON c.category_id = e.category_id
JOIN Organization o ON o.organization_id = e.donor_org_id
WHERE e.leftover > 0
  AND EXISTS (
        SELECT 1
        FROM RecipientRequest r
        WHERE r.category_id = e.category_id
          AND r.status <> 'cancelled'
          AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
          AND r.requested_at <= e.pickup_deadline
          AND r.needed_by    >= e.donated_at
          AND r.requested_quantity > COALESCE((SELECT SUM(a2.quantity_allocated)
                                               FROM Allocation a2
                                               WHERE a2.request_id = r.request_id
                                                 AND a2.status <> 'cancelled'), 0))
GROUP BY c.category_name, o.organization_name
ORDER BY avoidable_lost_servings DESC
LIMIT 25;

-- Q12 Structurally unmet demand - run 1
EXPLAIN (ANALYZE, BUFFERS)
WITH donation_remaining AS (
    SELECT d.donation_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE(SUM(a.quantity_allocated)
                                 FILTER (WHERE a.status <> 'cancelled'), 0) AS remaining
    FROM FoodDonation d
    LEFT JOIN Allocation a ON a.donation_id = d.donation_id
    WHERE d.status <> 'cancelled'
    GROUP BY d.donation_id, d.category_id, d.donated_at, d.pickup_deadline, d.quantity
), request_outstanding AS (
    SELECT r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
           r.requested_quantity - COALESCE(SUM(a.quantity_allocated)
                                           FILTER (WHERE a.status <> 'cancelled'), 0) AS outstanding
    FROM RecipientRequest r
    LEFT JOIN Allocation a ON a.request_id = r.request_id
    WHERE r.status IN ('open', 'partially_fulfilled', 'expired')
      AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
    GROUP BY r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
             r.requested_quantity
)
SELECT c.category_name,
       COUNT(*)                                    AS unmeetable_requests,
       COUNT(DISTINCT ro.recipient_org_id)          AS recipients_affected,
       SUM(ro.outstanding - ro.compatible_supply)   AS total_shortfall_servings
FROM (
    SELECT q.*,
           (SELECT COALESCE(SUM(dr.remaining), 0)
            FROM donation_remaining dr
            WHERE dr.category_id = q.category_id
              AND dr.donated_at <= q.needed_by
              AND dr.pickup_deadline >= q.requested_at) AS compatible_supply
    FROM request_outstanding q
    WHERE q.outstanding > 0
) ro
JOIN FoodCategory c ON c.category_id = ro.category_id
WHERE ro.outstanding > ro.compatible_supply
GROUP BY c.category_name
HAVING SUM(ro.outstanding - ro.compatible_supply) > 0
ORDER BY total_shortfall_servings DESC;

-- Q12 Structurally unmet demand - run 2
EXPLAIN (ANALYZE, BUFFERS)
WITH donation_remaining AS (
    SELECT d.donation_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE(SUM(a.quantity_allocated)
                                 FILTER (WHERE a.status <> 'cancelled'), 0) AS remaining
    FROM FoodDonation d
    LEFT JOIN Allocation a ON a.donation_id = d.donation_id
    WHERE d.status <> 'cancelled'
    GROUP BY d.donation_id, d.category_id, d.donated_at, d.pickup_deadline, d.quantity
), request_outstanding AS (
    SELECT r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
           r.requested_quantity - COALESCE(SUM(a.quantity_allocated)
                                           FILTER (WHERE a.status <> 'cancelled'), 0) AS outstanding
    FROM RecipientRequest r
    LEFT JOIN Allocation a ON a.request_id = r.request_id
    WHERE r.status IN ('open', 'partially_fulfilled', 'expired')
      AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
    GROUP BY r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
             r.requested_quantity
)
SELECT c.category_name,
       COUNT(*)                                    AS unmeetable_requests,
       COUNT(DISTINCT ro.recipient_org_id)          AS recipients_affected,
       SUM(ro.outstanding - ro.compatible_supply)   AS total_shortfall_servings
FROM (
    SELECT q.*,
           (SELECT COALESCE(SUM(dr.remaining), 0)
            FROM donation_remaining dr
            WHERE dr.category_id = q.category_id
              AND dr.donated_at <= q.needed_by
              AND dr.pickup_deadline >= q.requested_at) AS compatible_supply
    FROM request_outstanding q
    WHERE q.outstanding > 0
) ro
JOIN FoodCategory c ON c.category_id = ro.category_id
WHERE ro.outstanding > ro.compatible_supply
GROUP BY c.category_name
HAVING SUM(ro.outstanding - ro.compatible_supply) > 0
ORDER BY total_shortfall_servings DESC;

-- Q12 Structurally unmet demand - run 3
EXPLAIN (ANALYZE, BUFFERS)
WITH donation_remaining AS (
    SELECT d.donation_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE(SUM(a.quantity_allocated)
                                 FILTER (WHERE a.status <> 'cancelled'), 0) AS remaining
    FROM FoodDonation d
    LEFT JOIN Allocation a ON a.donation_id = d.donation_id
    WHERE d.status <> 'cancelled'
    GROUP BY d.donation_id, d.category_id, d.donated_at, d.pickup_deadline, d.quantity
), request_outstanding AS (
    SELECT r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
           r.requested_quantity - COALESCE(SUM(a.quantity_allocated)
                                           FILTER (WHERE a.status <> 'cancelled'), 0) AS outstanding
    FROM RecipientRequest r
    LEFT JOIN Allocation a ON a.request_id = r.request_id
    WHERE r.status IN ('open', 'partially_fulfilled', 'expired')
      AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '14 days'
    GROUP BY r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
             r.requested_quantity
)
SELECT c.category_name,
       COUNT(*)                                    AS unmeetable_requests,
       COUNT(DISTINCT ro.recipient_org_id)          AS recipients_affected,
       SUM(ro.outstanding - ro.compatible_supply)   AS total_shortfall_servings
FROM (
    SELECT q.*,
           (SELECT COALESCE(SUM(dr.remaining), 0)
            FROM donation_remaining dr
            WHERE dr.category_id = q.category_id
              AND dr.donated_at <= q.needed_by
              AND dr.pickup_deadline >= q.requested_at) AS compatible_supply
    FROM request_outstanding q
    WHERE q.outstanding > 0
) ro
JOIN FoodCategory c ON c.category_id = ro.category_id
WHERE ro.outstanding > ro.compatible_supply
GROUP BY c.category_name
HAVING SUM(ro.outstanding - ro.compatible_supply) > 0
ORDER BY total_shortfall_servings DESC;

