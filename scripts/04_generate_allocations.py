"""
04_generate_allocations.py - Simulate the donation -> request allocation
workflow on the cleaned data, then derive donation / request statuses.

Simulation (run separately for each food category, in time order):
  * When a donation is posted at time t, the requests of the same category
    that are already waiting (requested_at <= t < needed_by, remaining > 0)
    form the candidate pool.
  * The donation is split across 0-4 requests (urgent requests preferred).
    0 = nobody claimed it, which produces realistic food loss.
  * Business rules enforced (Project Outline s.4.6):
      - sum of active allocations <= donation quantity
      - sum of active allocations <= requested quantity
      - same category; allocated_at <= pickup_deadline, needed_by, AS_OF
      - picked_up_at <= pickup_deadline; delivered_at > picked_up_at
  * ~5% of allocations are cancelled (no-shows); cancelled quantity is
    released and does not count toward the caps.
  * Allocation status is derived from its timeline relative to AS_OF
    (pending -> confirmed -> picked_up -> delivered).

Status rules (relative to AS_OF = data snapshot time):
  FoodDonation     cancelled (2%, withdrawn before matching)
                   fully_allocated     active allocated == quantity
                   expired             pickup window closed with food left
                   partially_allocated some active allocation, window open
                   available           nothing allocated, window open
  RecipientRequest cancelled (2%, withdrawn before matching)
                   fulfilled           delivered >= requested
                   partially_fulfilled delivered/active allocation > 0 but < requested
                   expired             needed_by passed with nothing delivered
                   open                nothing allocated yet, deadline ahead

Outputs: data/processed/{organization,food_category,food_donation,
         recipient_request,allocation}.csv  (column order = SQL DDL)
"""

import random

import numpy as np
import pandas as pd

from common import AS_OF, FINAL_DIR, INTERIM_DIR, SEED

rng = np.random.default_rng(SEED + 40)

K_CHOICES = np.array([0, 1, 2, 3, 4])
K_PROBS = np.array([0.15, 0.40, 0.27, 0.12, 0.06])   # requests claimed per new donation
P_REQUEST_CLAIMS = 0.55                               # new request claims available food
P_CANCEL_ALLOC = 0.05
P_CANCEL_DONATION = 0.02
P_CANCEL_REQUEST = 0.02


def simulate(don: pd.DataFrame, req: pd.DataFrame) -> pd.DataFrame:
    """Two-sided, event-driven matching per category:
       * donation posted  -> may claim requests already waiting (K_PROBS)
       * request posted   -> may claim donations still available
         (P_REQUEST_CLAIMS, soonest pickup deadline preferred)
    Times are handled as integer seconds and scalar draws use `random`
    (seeded) because per-element numpy calls are ~50x slower here."""
    R = random.Random(SEED + 41)
    allocs = []
    asof = int(AS_OF.timestamp())
    k_cum = np.cumsum(K_PROBS).tolist()

    def secs(col):
        return (col.values.astype("datetime64[s]").astype(np.int64)).tolist()

    for cat_id in sorted(don.category_id.unique()):
        d = don[(don.category_id == cat_id) & ~don.cancelled]
        r = req[(req.category_id == cat_id) & ~req.cancelled]
        d_id, d_at, d_pdl = d.donation_id.tolist(), secs(d.donated_at), secs(d.pickup_deadline)
        d_rem = d.quantity.tolist()
        r_id, r_at, r_need = r.request_id.tolist(), secs(r.requested_at), secs(r.needed_by)
        r_rem = r.requested_quantity.tolist()

        def allocate(di, ri, t, q):
            alloc_at = t + int(R.uniform(0.25, 12) * 3600)
            if q <= 0 or alloc_at > min(d_pdl[di], r_need[ri], asof):
                return
            cancelled = R.random() < P_CANCEL_ALLOC
            if not cancelled:                   # cancelled quantity is released
                d_rem[di] -= q
                r_rem[ri] -= q
            # pickup between allocation and min(pickup deadline, +36 h)
            window = min(d_pdl[di], alloc_at + 36 * 3600) - alloc_at
            picked = alloc_at + int(window * R.uniform(0.1, 1.0))
            delivered = picked + int(R.uniform(0.3, 3) * 3600)
            allocs.append((d_id[di], r_id[ri], int(q), alloc_at, cancelled, picked, delivered))

        # merged event stream: (time, kind 0=request 1=donation, index)
        ev = sorted([(t, 0, i) for i, t in enumerate(r_at)] + [(t, 1, i) for i, t in enumerate(d_at)])
        r_pool: list[int] = []
        d_pool: list[int] = []
        for t, kind, idx in ev:
            if kind == 1:                                       # ---- donation posted
                r_pool = [i for i in r_pool if r_rem[i] > 0 and r_need[i] > t]
                u = R.random()
                k = min(next(n for n, c in enumerate(k_cum) if u <= c), len(r_pool))
                if k:
                    # urgent requests (close to needed_by) are preferred
                    w = [1.0 / max((r_need[i] - t) / 3600, 1.0) ** 0.5 for i in r_pool]
                    chosen = []
                    cand = list(range(len(r_pool)))
                    for _ in range(k):                          # weighted, no replacement
                        pick = R.choices(range(len(cand)), weights=[w[c] for c in cand])[0]
                        chosen.append(r_pool[cand.pop(pick)])
                    for n, ri in enumerate(chosen):
                        if d_rem[idx] <= 0:
                            break
                        if n == k - 1 and R.random() < 0.85:
                            q = min(r_rem[ri], d_rem[idx])
                        else:
                            q = min(r_rem[ri], max(1, round(d_rem[idx] * R.uniform(0.25, 0.7))))
                        allocate(idx, ri, t, q)
                if d_rem[idx] > 0:
                    d_pool.append(idx)
            else:                                               # ---- request posted
                d_pool = [i for i in d_pool if d_rem[i] > 0 and d_pdl[i] > t]
                if d_pool and R.random() < P_REQUEST_CLAIMS:
                    m = R.randint(1, 3)
                    for di in sorted(d_pool, key=d_pdl.__getitem__)[:m]:
                        if r_rem[idx] <= 0:
                            break
                        allocate(di, idx, t, min(r_rem[idx], d_rem[di]))
                r_pool.append(idx)
    a = pd.DataFrame(allocs, columns=["donation_id", "request_id", "quantity_allocated", "allocated_at",
                                      "cancelled", "picked", "delivered"])
    for c in ["allocated_at", "picked", "delivered"]:
        a[c] = pd.to_datetime(a[c], unit="s")
    # status from the timeline relative to the snapshot time
    status = np.select(
        [a.cancelled, a.allocated_at + pd.Timedelta(hours=2) > AS_OF, a.picked > AS_OF, a.delivered > AS_OF],
        ["cancelled", "pending", "confirmed", "picked_up"], default="delivered")
    a["status"] = status
    a["picked_up_at"] = a.picked.where(a.status.isin(["picked_up", "delivered"]))
    a["delivered_at"] = a.delivered.where(a.status == "delivered")
    a = a.sort_values(["allocated_at", "donation_id"]).reset_index(drop=True)
    a.insert(0, "allocation_id", np.arange(1, len(a) + 1))
    return a[["allocation_id", "donation_id", "request_id", "quantity_allocated", "allocated_at",
              "status", "picked_up_at", "delivered_at"]]


def derive_status(don, req, alloc):
    active = alloc[alloc.status != "cancelled"]
    d_act = active.groupby("donation_id").quantity_allocated.sum()
    r_act = active.groupby("request_id").quantity_allocated.sum()
    r_del = alloc[alloc.status == "delivered"].groupby("request_id").quantity_allocated.sum()

    da = don.donation_id.map(d_act).fillna(0)
    don["status"] = np.select(
        [don.cancelled, da >= don.quantity, don.pickup_deadline < AS_OF, da > 0],
        ["cancelled", "fully_allocated", "expired", "partially_allocated"], default="available")

    ra = req.request_id.map(r_act).fillna(0)
    rd = req.request_id.map(r_del).fillna(0)
    past = req.needed_by < AS_OF
    req["status"] = np.select(
        [req.cancelled, rd >= req.requested_quantity, past & (rd > 0), past, ra > 0],
        ["cancelled", "fulfilled", "partially_fulfilled", "expired", "partially_fulfilled"], default="open")
    return don, req


def fmt(df, cols):
    for c in cols:
        df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def main():
    ts_d = ["donated_at", "expires_at", "pickup_deadline"]
    ts_r = ["requested_at", "needed_by"]
    don = pd.read_csv(INTERIM_DIR / "donation_clean.csv", parse_dates=ts_d)
    req = pd.read_csv(INTERIM_DIR / "request_clean.csv", parse_dates=ts_r)

    # a few listings are withdrawn before anyone could claim them
    don["cancelled"] = rng.random(len(don)) < P_CANCEL_DONATION
    req["cancelled"] = rng.random(len(req)) < P_CANCEL_REQUEST

    alloc = simulate(don, req)
    don, req = derive_status(don, req, alloc)

    org = pd.read_csv(INTERIM_DIR / "organization.csv", dtype={"zip_code": str})
    cat = pd.read_csv(INTERIM_DIR / "food_category.csv")
    org.to_csv(FINAL_DIR / "organization.csv", index=False)
    cat.to_csv(FINAL_DIR / "food_category.csv", index=False)
    fmt(don, ts_d)[["donation_id", "donor_org_id", "category_id", "quantity", *ts_d, "status"]].to_csv(
        FINAL_DIR / "food_donation.csv", index=False)
    fmt(req, ts_r)[["request_id", "recipient_org_id", "category_id", "requested_quantity", *ts_r, "status"]].to_csv(
        FINAL_DIR / "recipient_request.csv", index=False)
    fmt(alloc, ["allocated_at", "picked_up_at", "delivered_at"]).replace("NaT", "").to_csv(
        FINAL_DIR / "allocation.csv", index=False)
    print(f"allocations {len(alloc)}")
    print(alloc.status.value_counts().to_string())
    print(don.status.value_counts().to_string())
    print(req.status.value_counts().to_string())


if __name__ == "__main__":
    main()
