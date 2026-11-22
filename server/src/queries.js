// All SQL used by the API. Q1-Q12 are the Milestone 3 queries, parameterized
// ($1, $2, ...) so user input is never concatenated into SQL. "now" ($n
// ::timestamp) comes from the application clock (config.now()).

// ---------------------------------------------------------------------------
// Q1. Organization directory search                     GET /organizations
// $1 role ('donor'|'recipient'|NULL)  $2 status  $3 zip  $4 search text
// $5 limit  $6 offset
// ---------------------------------------------------------------------------
const Q1_ORGANIZATIONS = `
SELECT o.organization_id, o.organization_name, o.organization_type,
       o.address, o.city, o.zip_code, o.contact_information, o.status,
       COUNT(*) OVER () AS total_count
FROM Organization o
WHERE ($1::text IS NULL OR o.organization_type IN ($1::text, 'both'))
  AND ($2::text IS NULL OR o.status = $2::text)
  AND ($3::text IS NULL OR o.zip_code = $3::text)
  AND ($4::text IS NULL OR o.organization_name ILIKE '%' || $4::text || '%')
ORDER BY o.organization_name, o.organization_id
LIMIT $5 OFFSET $6`;

// ---------------------------------------------------------------------------
// Q2. Claimable donations feed                     GET /donations/available
// $1 now  $2 category_id (NULL = all)  $3 limit
// ---------------------------------------------------------------------------
const Q2_AVAILABLE_DONATIONS = `
SELECT d.donation_id, d.donor_org_id, o.organization_name AS donor, o.zip_code AS donor_zip,
       d.category_id, c.category_name, c.storage_type,
       d.quantity,
       d.quantity - COALESCE(SUM(a.quantity_allocated)
                             FILTER (WHERE a.status <> 'cancelled'), 0) AS remaining_servings,
       d.donated_at, d.pickup_deadline, d.expires_at, d.status
FROM FoodDonation d
JOIN Organization o ON o.organization_id = d.donor_org_id
JOIN FoodCategory c ON c.category_id = d.category_id
LEFT JOIN Allocation a ON a.donation_id = d.donation_id
WHERE d.status IN ('available', 'partially_allocated')
  AND d.pickup_deadline > $1::timestamp
  AND ($2::int IS NULL OR d.category_id = $2::int)
GROUP BY d.donation_id, o.organization_name, o.zip_code, c.category_name, c.storage_type
ORDER BY d.pickup_deadline
LIMIT $3`;

// ---------------------------------------------------------------------------
// Q3. Donor profile summary          GET /organizations/:id/donation-summary
// $1 organization_id
// ---------------------------------------------------------------------------
const Q3_DONOR_SUMMARY = `
SELECT c.category_id, c.category_name,
       COUNT(*)                  AS donations,
       SUM(d.quantity)           AS servings_donated,
       ROUND(AVG(d.quantity), 1) AS avg_servings
FROM FoodDonation d
JOIN FoodCategory c ON c.category_id = d.category_id
WHERE d.donor_org_id = $1
GROUP BY c.category_id, c.category_name
ORDER BY servings_donated DESC`;

// ---------------------------------------------------------------------------
// Q4. Request tracking                         GET /requests/:id/allocations
// $1 request_id
// ---------------------------------------------------------------------------
const Q4_REQUEST_ALLOCATIONS = `
SELECT a.allocation_id, a.donation_id, d.donor_org_id, o.organization_name AS donor,
       a.quantity_allocated, a.status, a.allocated_at, a.picked_up_at, a.delivered_at
FROM Allocation a
JOIN FoodDonation d ON d.donation_id = a.donation_id
JOIN Organization o ON o.organization_id = d.donor_org_id
WHERE a.request_id = $1
ORDER BY a.allocated_at, a.allocation_id`;

// ---------------------------------------------------------------------------
// Q5. Platform KPIs                                       GET /dashboard/kpis
// ---------------------------------------------------------------------------
const Q5_KPIS = `
SELECT COUNT(*)                                                    AS total_allocations,
       COUNT(*) FILTER (WHERE status = 'delivered')                AS delivered_allocations,
       COALESCE(SUM(quantity_allocated) FILTER (WHERE status = 'delivered'), 0)
                                                                   AS servings_delivered,
       COALESCE(SUM(quantity_allocated)
                FILTER (WHERE status IN ('pending', 'confirmed', 'picked_up')), 0)
                                                                   AS servings_in_transit,
       COUNT(*) FILTER (WHERE status = 'cancelled')                AS cancelled_allocations
FROM Allocation`;

// ---------------------------------------------------------------------------
// Q6. Category demand in the last N days                GET /categories/demand
// $1 now  $2 days
// ---------------------------------------------------------------------------
const Q6_CATEGORY_DEMAND = `
SELECT c.category_id, c.category_name, c.storage_type,
       COUNT(r.request_id)       AS requests,
       SUM(r.requested_quantity) AS servings_requested
FROM FoodCategory c
JOIN RecipientRequest r ON r.category_id = c.category_id
WHERE r.requested_at >= $1::timestamp - make_interval(days => $2::int)
  AND r.requested_at <= $1::timestamp
  AND r.status <> 'cancelled'
GROUP BY c.category_id, c.category_name, c.storage_type
ORDER BY servings_requested DESC`;

// ---------------------------------------------------------------------------
// Q7. Monthly supply, demand and fulfilment     GET /analytics/monthly-fulfillment
// $1 category_id (NULL = all)  $2 first month (date)  $3 last month (date)
// ---------------------------------------------------------------------------
const Q7_MONTHLY_FULFILLMENT = `
WITH supply AS (
    SELECT date_trunc('month', donated_at) AS month, category_id,
           SUM(quantity) AS donated
    FROM FoodDonation
    WHERE status <> 'cancelled'
      AND ($1::int IS NULL OR category_id = $1::int)
      AND donated_at >= $2::date AND donated_at < $3::date + INTERVAL '1 month'
    GROUP BY 1, 2
), demand AS (
    SELECT date_trunc('month', requested_at) AS month, category_id,
           SUM(requested_quantity) AS requested
    FROM RecipientRequest
    WHERE status <> 'cancelled'
      AND ($1::int IS NULL OR category_id = $1::int)
      AND requested_at >= $2::date AND requested_at < $3::date + INTERVAL '1 month'
    GROUP BY 1, 2
), delivered AS (
    SELECT date_trunc('month', r.requested_at) AS month, r.category_id,
           SUM(a.quantity_allocated) AS delivered
    FROM Allocation a
    JOIN RecipientRequest r ON r.request_id = a.request_id
    WHERE a.status = 'delivered'
      AND ($1::int IS NULL OR r.category_id = $1::int)
      AND r.requested_at >= $2::date AND r.requested_at < $3::date + INTERVAL '1 month'
    GROUP BY 1, 2
)
SELECT to_char(COALESCE(s.month, dm.month), 'YYYY-MM')       AS month,
       c.category_id, c.category_name,
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
ORDER BY month, c.category_name`;

// ---------------------------------------------------------------------------
// Q8. Donor performance benchmarking          GET /analytics/donor-leaderboard
// $1 min_donations  $2 limit
// ---------------------------------------------------------------------------
const Q8_DONOR_LEADERBOARD = `
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
    HAVING COUNT(*) >= $1
)
SELECT RANK() OVER (ORDER BY servings_delivered DESC) AS rank_by_delivered,
       organization_id, organization_name, zip_code, donations,
       servings_donated, servings_delivered, delivery_rate_pct,
       ROUND(delivery_rate_pct - (SELECT 100.0 * SUM(delivered) / SUM(quantity)
                                  FROM donation_outcome), 1) AS vs_platform_pct_points
FROM donor_stats
ORDER BY rank_by_delivered, organization_id
LIMIT $2`;

// ---------------------------------------------------------------------------
// Q9. Geographic distribution gaps                    GET /analytics/zip-gaps
// $1 limit
// ---------------------------------------------------------------------------
const Q9_ZIP_GAPS = `
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
SELECT RANK() OVER (ORDER BY n.unmet_servings::numeric
                    / GREATEST(COALESCE(s.active_recipient_sites, 0), 1) DESC) AS gap_rank,
       n.zip_code, n.unmet_servings, n.unmet_requests,
       COALESCE(s.active_recipient_sites, 0)          AS active_recipient_sites,
       COALESCE(sp.servings_donated_locally, 0)        AS servings_donated_locally,
       ROUND(n.unmet_servings::numeric / GREATEST(COALESCE(s.active_recipient_sites, 0), 1), 0)
                                                       AS unmet_per_site
FROM zip_need n
LEFT JOIN zip_sites s  ON s.zip_code = n.zip_code
LEFT JOIN zip_supply sp ON sp.zip_code = n.zip_code
ORDER BY gap_rank, n.zip_code
LIMIT $1`;

// ---------------------------------------------------------------------------
// Q10. Avoidable food loss                       GET /analytics/avoidable-loss
// $1 now  $2 days  $3 limit
// ---------------------------------------------------------------------------
const Q10_AVOIDABLE_LOSS = `
WITH expired_leftover AS (
    SELECT d.donation_id, d.donor_org_id, d.category_id, d.donated_at, d.pickup_deadline,
           d.quantity - COALESCE((SELECT SUM(a.quantity_allocated)
                                  FROM Allocation a
                                  WHERE a.donation_id = d.donation_id
                                    AND a.status <> 'cancelled'), 0) AS leftover
    FROM FoodDonation d
    WHERE d.status = 'expired'
      AND d.donated_at >= $1::timestamp - make_interval(days => $2::int)
)
SELECT c.category_id, c.category_name, o.organization_id AS donor_org_id,
       o.organization_name AS donor,
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
          AND r.requested_at >= $1::timestamp - make_interval(days => $2::int)
          AND r.requested_at <= e.pickup_deadline
          AND r.needed_by    >= e.donated_at
          AND r.requested_quantity > COALESCE((SELECT SUM(a2.quantity_allocated)
                                               FROM Allocation a2
                                               WHERE a2.request_id = r.request_id
                                                 AND a2.status <> 'cancelled'), 0))
GROUP BY c.category_id, c.category_name, o.organization_id, o.organization_name
ORDER BY avoidable_lost_servings DESC, donor_org_id
LIMIT $3`;

// ---------------------------------------------------------------------------
// Q11. Fully served recipients          GET /analytics/fully-served-recipients
// $1 now  $2 days
// ---------------------------------------------------------------------------
const Q11_FULLY_SERVED = `
SELECT o.organization_id, o.organization_name, o.zip_code,
       COUNT(DISTINCT r.category_id) AS categories_requested,
       COUNT(DISTINCT r.request_id)  AS requests,
       (SELECT SUM(a.quantity_allocated)
        FROM Allocation a
        JOIN RecipientRequest r3 ON r3.request_id = a.request_id
        WHERE r3.recipient_org_id = o.organization_id
          AND a.status = 'delivered'
          AND r3.requested_at >= $1::timestamp - make_interval(days => $2::int)) AS servings_received
FROM Organization o
JOIN RecipientRequest r
  ON r.recipient_org_id = o.organization_id
 AND r.status <> 'cancelled'
 AND r.requested_at >= $1::timestamp - make_interval(days => $2::int)
WHERE o.status = 'active'
  AND o.organization_type IN ('recipient', 'both')
  AND NOT EXISTS (                       -- there is no requested category ...
        SELECT 1
        FROM RecipientRequest r1
        WHERE r1.recipient_org_id = o.organization_id
          AND r1.status <> 'cancelled'
          AND r1.requested_at >= $1::timestamp - make_interval(days => $2::int)
          AND NOT EXISTS (               -- ... that never received a delivery
                SELECT 1
                FROM Allocation a
                JOIN RecipientRequest r2 ON r2.request_id = a.request_id
                WHERE r2.recipient_org_id = o.organization_id
                  AND r2.category_id = r1.category_id
                  AND r2.requested_at >= $1::timestamp - make_interval(days => $2::int)
                  AND a.status = 'delivered'))
GROUP BY o.organization_id, o.organization_name, o.zip_code
ORDER BY categories_requested DESC, servings_received DESC NULLS LAST, o.organization_id`;

// ---------------------------------------------------------------------------
// Q12. Structurally unmet demand                   GET /analytics/unmet-demand
// $1 now  $2 days
// ---------------------------------------------------------------------------
const Q12_UNMET_DEMAND = `
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
      AND r.requested_at >= $1::timestamp - make_interval(days => $2::int)
    GROUP BY r.request_id, r.recipient_org_id, r.category_id, r.requested_at, r.needed_by,
             r.requested_quantity
)
SELECT c.category_id, c.category_name,
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
GROUP BY c.category_id, c.category_name
HAVING SUM(ro.outstanding - ro.compatible_supply) > 0
ORDER BY total_shortfall_servings DESC`;

// ===========================================================================
// Auxiliary statements
// ===========================================================================
const CATEGORIES = `
SELECT category_id, category_name, storage_type, description
FROM FoodCategory
ORDER BY category_name`;

const ORGANIZATION_BY_ID = `
SELECT organization_id, organization_name, organization_type, address, city,
       zip_code, contact_information, status
FROM Organization
WHERE organization_id = $1`;

const REQUEST_BY_ID = `
SELECT request_id, recipient_org_id, category_id, requested_quantity,
       requested_at, needed_by, status
FROM RecipientRequest
WHERE request_id = $1`;

const CATEGORY_EXISTS = `SELECT 1 FROM FoodCategory WHERE category_id = $1`;

// $1 donor_org_id $2 category_id $3 quantity $4 donated_at(now) $5 expires_at $6 pickup_deadline
const INSERT_DONATION = `
INSERT INTO FoodDonation (donor_org_id, category_id, quantity, donated_at,
                          expires_at, pickup_deadline, status)
VALUES ($1, $2, $3, $4::timestamp, $5::timestamp, $6::timestamp, 'available')
RETURNING donation_id, donor_org_id, category_id, quantity, donated_at,
          expires_at, pickup_deadline, status`;

// $1 recipient_org_id $2 category_id $3 requested_quantity $4 requested_at(now) $5 needed_by
const INSERT_REQUEST = `
INSERT INTO RecipientRequest (recipient_org_id, category_id, requested_quantity,
                              requested_at, needed_by, status)
VALUES ($1, $2, $3, $4::timestamp, $5::timestamp, 'open')
RETURNING request_id, recipient_org_id, category_id, requested_quantity,
          requested_at, needed_by, status`;

// Locked reads used inside the allocation transaction
const LOCK_DONATION = `
SELECT d.donation_id, d.category_id, d.quantity, d.status, d.pickup_deadline,
       d.quantity - COALESCE((SELECT SUM(a.quantity_allocated) FROM Allocation a
                              WHERE a.donation_id = d.donation_id
                                AND a.status <> 'cancelled'), 0) AS remaining
FROM FoodDonation d
WHERE d.donation_id = $1
FOR UPDATE`;

const LOCK_REQUEST = `
SELECT r.request_id, r.category_id, r.requested_quantity, r.status, r.needed_by,
       r.requested_quantity - COALESCE((SELECT SUM(a.quantity_allocated) FROM Allocation a
                                        WHERE a.request_id = r.request_id
                                          AND a.status <> 'cancelled'), 0) AS outstanding
FROM RecipientRequest r
WHERE r.request_id = $1
FOR UPDATE`;

const LOCK_ALLOCATION = `
SELECT allocation_id, donation_id, request_id, quantity_allocated, allocated_at,
       status, picked_up_at, delivered_at
FROM Allocation
WHERE allocation_id = $1
FOR UPDATE`;

// $1 donation_id $2 request_id $3 quantity $4 now
const INSERT_ALLOCATION = `
INSERT INTO Allocation (donation_id, request_id, quantity_allocated, allocated_at, status)
VALUES ($1, $2, $3, $4::timestamp, 'pending')
RETURNING allocation_id, donation_id, request_id, quantity_allocated, allocated_at,
          status, picked_up_at, delivered_at`;

// $1 allocation_id $2 new status $3 now
const UPDATE_ALLOCATION_STATUS = `
UPDATE Allocation
SET status       = $2::text,
    picked_up_at = CASE WHEN $2::text = 'picked_up' THEN $3::timestamp ELSE picked_up_at END,
    delivered_at = CASE WHEN $2::text = 'delivered' THEN $3::timestamp ELSE delivered_at END
WHERE allocation_id = $1
RETURNING allocation_id, donation_id, request_id, quantity_allocated, allocated_at,
          status, picked_up_at, delivered_at`;

// Re-derive a donation's status from its allocations (same rules as the data pipeline)
// $1 donation_id $2 now
const REFRESH_DONATION_STATUS = `
UPDATE FoodDonation d
SET status = CASE
        WHEN d.status = 'cancelled'           THEN 'cancelled'
        WHEN s.active >= d.quantity           THEN 'fully_allocated'
        WHEN d.pickup_deadline < $2::timestamp THEN 'expired'
        WHEN s.active > 0                     THEN 'partially_allocated'
        ELSE 'available' END
FROM (SELECT COALESCE(SUM(quantity_allocated) FILTER (WHERE status <> 'cancelled'), 0) AS active
      FROM Allocation WHERE donation_id = $1) s
WHERE d.donation_id = $1
RETURNING d.donation_id, d.status`;

// $1 request_id $2 now
const REFRESH_REQUEST_STATUS = `
UPDATE RecipientRequest r
SET status = CASE
        WHEN r.status = 'cancelled'                                THEN 'cancelled'
        WHEN s.delivered >= r.requested_quantity                    THEN 'fulfilled'
        WHEN r.needed_by < $2::timestamp AND s.delivered > 0        THEN 'partially_fulfilled'
        WHEN r.needed_by < $2::timestamp                            THEN 'expired'
        WHEN s.active > 0                                           THEN 'partially_fulfilled'
        ELSE 'open' END
FROM (SELECT COALESCE(SUM(quantity_allocated) FILTER (WHERE status <> 'cancelled'), 0) AS active,
             COALESCE(SUM(quantity_allocated) FILTER (WHERE status = 'delivered'), 0) AS delivered
      FROM Allocation WHERE request_id = $1) s
WHERE r.request_id = $1
RETURNING r.request_id, r.status`;

module.exports = {
  Q1_ORGANIZATIONS, Q2_AVAILABLE_DONATIONS, Q3_DONOR_SUMMARY, Q4_REQUEST_ALLOCATIONS,
  Q5_KPIS, Q6_CATEGORY_DEMAND, Q7_MONTHLY_FULFILLMENT, Q8_DONOR_LEADERBOARD,
  Q9_ZIP_GAPS, Q10_AVOIDABLE_LOSS, Q11_FULLY_SERVED, Q12_UNMET_DEMAND,
  CATEGORIES, ORGANIZATION_BY_ID, REQUEST_BY_ID, CATEGORY_EXISTS,
  INSERT_DONATION, INSERT_REQUEST, LOCK_DONATION, LOCK_REQUEST, LOCK_ALLOCATION,
  INSERT_ALLOCATION, UPDATE_ALLOCATION_STATUS, REFRESH_DONATION_STATUS, REFRESH_REQUEST_STATUS,
};
