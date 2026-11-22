# Optimization notes

## Baseline on AWS RDS (2026-11-22, `sql/measure_runtime.sql`)

These are `EXPLAIN (ANALYZE, BUFFERS)` execution times with only primary-key indexes, 3 runs per query.

| Query | Run 1 (cold) | Run 2 | Run 3 | Average |
|---|---:|---:|---:|---:|
| Q10 avoidable food loss | 115.7 s | 112.0 s | 113.5 s | **113.7 s (1.9 min)** |
| Q12 structurally unmet demand | 178.7 s | 177.3 s | 179.0 s | **178.3 s (3.0 min)** |

The warm runs are no faster than the cold run, so the cost is CPU work in the plan (repeated sequential scans and re-aggregation), not disk reads. The RDS instance is about 2.5× slower than the local test machine.

## Preliminary local measurements (2026-11-10, local PostgreSQL 16, 2 vCPU)

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
