-- =============================================================================
-- FoodBridge - Milestone 3 SQL queries (CIS 5500, Group 25)
-- Reference time: the dataset is a snapshot taken at 2026-11-10 12:00:00, so
-- "now" is the literal TIMESTAMP '2026-11-10 12:00:00' (an :as_of parameter in
-- the API). Literal ids / ZIPs / dates below are example parameter values.
-- Q1-Q6 simple (one page feature each), Q7-Q12 complex.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. Organization directory search (Organizations page)
-- Active recipient organizations in a ZIP code whose name matches a search
-- term, alphabetically.
-- -----------------------------------------------------------------------------
SELECT o.organization_id, o.organization_name, o.organization_type,
       o.address, o.zip_code, o.contact_information
FROM Organization o
WHERE o.status = 'active'
  AND o.organization_type IN ('recipient', 'both')
  AND o.zip_code = '19140'
  AND o.organization_name ILIKE '%church%'
ORDER BY o.organization_name;


-- -----------------------------------------------------------------------------
-- Q2. Claimable donations feed (Food Donations page)
-- Donations that can still be picked up at the reference time, with donor,
-- category, storage type and the servings not yet allocated, soonest
-- pickup deadline first.
-- -----------------------------------------------------------------------------
SELECT d.donation_id, o.organization_name AS donor, c.category_name, c.storage_type,
       d.quantity,
       d.quantity - COALESCE(SUM(a.quantity_allocated)
                             FILTER (WHERE a.status <> 'cancelled'), 0) AS remaining_servings,
       d.pickup_deadline, d.expires_at
FROM FoodDonation d
JOIN Organization o ON o.organization_id = d.donor_org_id
JOIN FoodCategory c ON c.category_id = d.category_id
LEFT JOIN Allocation a ON a.donation_id = d.donation_id
WHERE d.status IN ('available', 'partially_allocated')
  AND d.pickup_deadline > TIMESTAMP '2026-11-10 12:00:00'
GROUP BY d.donation_id, o.organization_name, c.category_name, c.storage_type
ORDER BY d.pickup_deadline
LIMIT 50;


-- -----------------------------------------------------------------------------
-- Q3. Donor profile summary (Organization detail page)
-- For one donor organization: number of donations, servings donated and
-- average donation size per food category.
-- -----------------------------------------------------------------------------
SELECT c.category_name,
       COUNT(*)                  AS donations,
       SUM(d.quantity)           AS servings_donated,
       ROUND(AVG(d.quantity), 1) AS avg_servings
FROM FoodDonation d
JOIN FoodCategory c ON c.category_id = d.category_id
WHERE d.donor_org_id = 400
GROUP BY c.category_name
ORDER BY servings_donated DESC;


-- -----------------------------------------------------------------------------
-- Q4. Request tracking (Recipient Requests page)
-- Every allocation made against one request: which donor supplied it, how
-- many servings, and its pickup / delivery status and times.
-- -----------------------------------------------------------------------------
SELECT a.allocation_id, o.organization_name AS donor, a.quantity_allocated,
       a.status, a.allocated_at, a.picked_up_at, a.delivered_at
FROM Allocation a
JOIN FoodDonation d ON d.donation_id = a.donation_id
JOIN Organization o ON o.organization_id = d.donor_org_id
WHERE a.request_id = 100006
ORDER BY a.allocated_at;


-- -----------------------------------------------------------------------------
-- Q5. Platform KPIs (Dashboard)
-- Headline numbers in one row: allocation counts and servings delivered,
-- servings in transit and number of cancelled allocations.
-- -----------------------------------------------------------------------------
SELECT COUNT(*)                                                       AS total_allocations,
       COUNT(*) FILTER (WHERE status = 'delivered')                   AS delivered_allocations,
       SUM(quantity_allocated) FILTER (WHERE status = 'delivered')    AS servings_delivered,
       SUM(quantity_allocated) FILTER (WHERE status IN ('pending', 'confirmed', 'picked_up'))
                                                                      AS servings_in_transit,
       COUNT(*) FILTER (WHERE status = 'cancelled')                   AS cancelled_allocations
FROM Allocation;


-- -----------------------------------------------------------------------------
-- Q6. Category demand in the last 30 days (Dashboard / Requests page)
-- Requests and requested servings per food category over the 30 days
-- before the reference time, busiest categories first.
-- -----------------------------------------------------------------------------
SELECT c.category_name, c.storage_type,
       COUNT(r.request_id)       AS requests,
       SUM(r.requested_quantity) AS servings_requested
FROM FoodCategory c
JOIN RecipientRequest r ON r.category_id = c.category_id
WHERE r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '30 days'
  AND r.status <> 'cancelled'
GROUP BY c.category_name, c.storage_type
ORDER BY servings_requested DESC;


-- =============================================================================
-- Complex queries
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Q7. Monthly supply, demand and fulfilment by category (Analytics page)
-- For each month and food category: servings donated, servings requested,
-- servings actually delivered, and the share of demand that was met.
-- [3 CTEs with aggregation, joins through Allocation, FULL OUTER JOIN]
-- -----------------------------------------------------------------------------
WITH supply AS (
    SELECT date_trunc('month', donated_at) AS month, category_id,
           SUM(quantity) AS donated
    FROM FoodDonation
    WHERE status <> 'cancelled'
    GROUP BY 1, 2
), demand AS (
    SELECT date_trunc('month', requested_at) AS month, category_id,
           SUM(requested_quantity) AS requested
    FROM RecipientRequest
    WHERE status <> 'cancelled'
    GROUP BY 1, 2
), delivered AS (
    SELECT date_trunc('month', r.requested_at) AS month, r.category_id,
           SUM(a.quantity_allocated) AS delivered
    FROM Allocation a
    JOIN RecipientRequest r ON r.request_id = a.request_id
    WHERE a.status = 'delivered'
    GROUP BY 1, 2
)
SELECT to_char(COALESCE(s.month, dm.month), 'YYYY-MM')       AS month,
       c.category_name,
       COALESCE(s.donated, 0)                                 AS servings_donated,
       COALESCE(dm.requested, 0)                              AS servings_requested,
       COALESCE(dl.delivered, 0)                              AS servings_delivered,
       ROUND(100.0 * COALESCE(dl.delivered, 0) / NULLIF(dm.requested, 0), 1) AS demand_met_pct
FROM supply s
FULL OUTER JOIN demand dm ON dm.month = s.month AND dm.category_id = s.category_id
LEFT JOIN delivered dl
       ON dl.month = COALESCE(s.month, dm.month)
      AND dl.category_id = COALESCE(s.category_id, dm.category_id)
JOIN FoodCategory c ON c.category_id = COALESCE(s.category_id, dm.category_id)
ORDER BY month, c.category_name;


-- -----------------------------------------------------------------------------
-- Q8. Donor performance benchmarking (Analytics page - donor leaderboard)
-- For donors with at least 20 donations: servings donated, servings that
-- reached a recipient, delivery rate, how that rate compares with the
-- platform-wide rate, and the donor's rank.
-- [CTE + 3-table join, GROUP BY/HAVING, scalar subquery, window function]
-- -----------------------------------------------------------------------------
WITH donation_outcome AS (
    SELECT d.donation_id, d.donor_org_id, d.quantity,
           COALESCE(SUM(a.quantity_allocated) FILTER (WHERE a.status = 'delivered'), 0) AS delivered
    FROM FoodDonation d
    LEFT JOIN Allocation a ON a.donation_id = d.donation_id
    WHERE d.status <> 'cancelled'
    GROUP BY d.donation_id, d.donor_org_id, d.quantity
), donor_stats AS (
    SELECT o.organization_id, o.organization_name, o.zip_code,
           COUNT(*)            AS donations,
           SUM(x.quantity)     AS servings_donated,
           SUM(x.delivered)    AS servings_delivered,
           ROUND(100.0 * SUM(x.delivered) / SUM(x.quantity), 1) AS delivery_rate_pct
    FROM donation_outcome x
    JOIN Organization o ON o.organization_id = x.donor_org_id
    GROUP BY o.organization_id, o.organization_name, o.zip_code
    HAVING COUNT(*) >= 20
)
SELECT RANK() OVER (ORDER BY servings_delivered DESC) AS rank_by_delivered,
       organization_name, zip_code, donations, servings_donated, servings_delivered,
       delivery_rate_pct,
       ROUND(delivery_rate_pct - (SELECT 100.0 * SUM(delivered) / SUM(quantity)
                                  FROM donation_outcome), 1) AS vs_platform_pct_points
FROM donor_stats
ORDER BY rank_by_delivered
LIMIT 25;


-- -----------------------------------------------------------------------------
-- Q9. Geographic distribution gaps (Analytics page - map)
-- For each ZIP code: outstanding (requested minus delivered) servings of
-- requests that are past their deadline or still open, the number of
-- active recipient sites, servings donated by donors located there, and
-- unmet servings per site. ZIPs ranked by unmet need per site.
-- [CTEs, LEFT/outer joins, nested aggregation, derived ratio, window rank]
-- -----------------------------------------------------------------------------
WITH request_outstanding AS (
    SELECT r.request_id, r.recipient_org_id,
           r.requested_quantity
             - COALESCE(SUM(a.quantity_allocated) FILTER (WHERE a.status = 'delivered'), 0) AS outstanding
    FROM RecipientRequest r
    LEFT JOIN Allocation a ON a.request_id = r.request_id
    WHERE r.status IN ('open', 'partially_fulfilled', 'expired')
    GROUP BY r.request_id, r.recipient_org_id, r.requested_quantity
), zip_need AS (
    SELECT o.zip_code, SUM(ro.outstanding) AS unmet_servings,
           COUNT(*) FILTER (WHERE ro.outstanding > 0) AS unmet_requests
    FROM request_outstanding ro
    JOIN Organization o ON o.organization_id = ro.recipient_org_id
    WHERE o.zip_code IS NOT NULL
    GROUP BY o.zip_code
), zip_sites AS (
    SELECT zip_code, COUNT(*) AS active_recipient_sites
    FROM Organization
    WHERE status = 'active' AND organization_type IN ('recipient', 'both')
    GROUP BY zip_code
), zip_supply AS (
    SELECT o.zip_code, SUM(d.quantity) AS servings_donated_locally
    FROM FoodDonation d
    JOIN Organization o ON o.organization_id = d.donor_org_id
    GROUP BY o.zip_code
)
SELECT n.zip_code, n.unmet_servings, n.unmet_requests,
       COALESCE(s.active_recipient_sites, 0)          AS active_recipient_sites,
       COALESCE(sp.servings_donated_locally, 0)        AS servings_donated_locally,
       ROUND(n.unmet_servings::numeric / GREATEST(COALESCE(s.active_recipient_sites, 0), 1), 0)
                                                       AS unmet_per_site,
       RANK() OVER (ORDER BY n.unmet_servings::numeric
                    / GREATEST(COALESCE(s.active_recipient_sites, 0), 1) DESC) AS gap_rank
FROM zip_need n
LEFT JOIN zip_sites s  ON s.zip_code = n.zip_code
LEFT JOIN zip_supply sp ON sp.zip_code = n.zip_code
ORDER BY gap_rank;


-- -----------------------------------------------------------------------------
-- Q10. Avoidable food loss (Analytics page - wastage)  [slow before tuning]
-- Donations posted in the 14 days before the reference time that expired with
-- servings left over even though at least one compatible request posted in
-- the same period existed: same category, open during the donation's pickup
-- window, and still short of servings. Leftover servings are summed per
-- category and donor.
-- [EXISTS check with correlated subqueries, CTE, joins, aggregation]
-- -----------------------------------------------------------------------------
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


-- -----------------------------------------------------------------------------
-- Q11. Fully served recipients (Analytics page - recipient coverage)
--      [universal quantification, slow before tuning]
-- Active recipient organizations that, in the 180 days before the reference
-- time, received at least one delivered allocation in EVERY food category
-- they requested ("for all requested categories, a delivery exists"), with
-- the number of categories, requests and servings received.
-- [double NOT EXISTS (relational division), correlated subqueries, joins, aggregation]
-- -----------------------------------------------------------------------------
SELECT o.organization_id, o.organization_name, o.zip_code,
       COUNT(DISTINCT r.category_id) AS categories_requested,
       COUNT(DISTINCT r.request_id)  AS requests,
       (SELECT SUM(a.quantity_allocated)
        FROM Allocation a
        JOIN RecipientRequest r3 ON r3.request_id = a.request_id
        WHERE r3.recipient_org_id = o.organization_id
          AND a.status = 'delivered'
          AND r3.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '180 days') AS servings_received
FROM Organization o
JOIN RecipientRequest r
  ON r.recipient_org_id = o.organization_id
 AND r.status <> 'cancelled'
 AND r.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '180 days'
WHERE o.status = 'active'
  AND o.organization_type IN ('recipient', 'both')
  AND NOT EXISTS (                       -- there is no requested category ...
        SELECT 1
        FROM RecipientRequest r1
        WHERE r1.recipient_org_id = o.organization_id
          AND r1.status <> 'cancelled'
          AND r1.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '180 days'
          AND NOT EXISTS (               -- ... that never received a delivery
                SELECT 1
                FROM Allocation a
                JOIN RecipientRequest r2 ON r2.request_id = a.request_id
                WHERE r2.recipient_org_id = o.organization_id
                  AND r2.category_id = r1.category_id
                  AND r2.requested_at >= TIMESTAMP '2026-11-10 12:00:00' - INTERVAL '180 days'
                  AND a.status = 'delivered'))
GROUP BY o.organization_id, o.organization_name, o.zip_code
ORDER BY categories_requested DESC, servings_received DESC;


-- -----------------------------------------------------------------------------
-- Q12. Structurally unmet demand (Recipient Requests page - "at risk" list,
--      Analytics page)  [slow before tuning]
-- Requests posted in the 14 days before the reference time whose outstanding
-- servings exceed ALL remaining (unallocated) servings of compatible
-- donations: same category, posted before the request's deadline and still
-- collectable after the request was made. Reported per category with the
-- number of such requests, recipients affected and the total shortfall.
-- [2 CTEs with LEFT JOIN aggregation, correlated subquery, joins, HAVING]
-- -----------------------------------------------------------------------------
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
