# Optimization notes (preliminary, measured 2026-11-10 on a local PostgreSQL 16, 2 vCPU)

These baseline measurements were taken on a local copy with no indexes beyond the primary keys. Re-measure on RDS with `EXPLAIN ANALYZE` for the final report, because RDS will be slower.

| Query | No extra indexes | With indexes | Notes |
|---|---:|---:|---|
| Q7 monthly supply/demand | 0.16 s | – | Hash joins, already fast |
| Q8 donor benchmarking | 0.29 s | – | |
| Q9 ZIP gaps | 0.16 s | – | |
| **Q10 avoidable food loss** | **47 s** | **0.06 s** | The correlated `SUM` over Allocation did a full Seq Scan for every row. Indexes on `Allocation(donation_id)` and `Allocation(request_id)` turn it into an index lookup. |
| Q11 fully served recipients | 2.9 s | 1.2 s | The NOT EXISTS becomes a hashed subplan, so it is moderately fast |
| **Q12 structurally unmet demand** | **71 s** | **27 s** | Indexes alone are not enough. PostgreSQL inlines the single-use CTE `donation_remaining` into the correlated subquery and recomputes it for every request. |
| Q12 restructured + indexes | – | **0.10 s** | `donation_remaining AS MATERIALIZED`, pre-filtered on `pickup_deadline >= as_of - 14 days`, then a LEFT JOIN + GROUP BY in place of the correlated subquery (same 16 result rows) |

Candidate indexes tested:

```sql
CREATE INDEX ix_alloc_donation  ON Allocation(donation_id);
CREATE INDEX ix_alloc_request   ON Allocation(request_id);
CREATE INDEX ix_req_cat_time    ON RecipientRequest(category_id, requested_at);
CREATE INDEX ix_don_status_time ON FoodDonation(status, donated_at);
```

Still to do for the report:
- Run `EXPLAIN ANALYZE` before and after each change.
- Test each index on its own to see which ones actually matter.
- Add caching in the API (e.g. for Q7/Q9 dashboard data, which changes rarely).
