# FoodBridge - final dataset summary

Snapshot time (AS_OF): 2026-11-10 12:00:00. Activity window: 2025-01-02 to 2026-11-10 11:57.

## Table sizes

| table            |   rows |   attributes |   csv size (MB) |
|:-----------------|-------:|-------------:|----------------:|
| Organization     |   1000 |            8 |            0.12 |
| FoodCategory     |     25 |            4 |            0    |
| FoodDonation     | 150000 |            8 |           13.23 |
| RecipientRequest | 120000 |            7 |            8.18 |
| Allocation       | 198415 |            8 |           17.81 |

**Total rows: 469,440**

## Numeric attributes (servings)

| attribute                           |      n |   mean |   median |   std |   min |   max |
|:------------------------------------|-------:|-------:|---------:|------:|------:|------:|
| FoodDonation.quantity               | 150000 |  63.22 |       45 | 62.53 |     3 |  1500 |
| RecipientRequest.requested_quantity | 120000 | 113.59 |       95 | 74.66 |     7 |  1183 |
| Allocation.quantity_allocated       | 198415 |  33.82 |       24 | 32.58 |     1 |   615 |

| attribute                |      n |   mean |   median |    std |   min |    max |
|:-------------------------|-------:|-------:|---------:|-------:|------:|-------:|
| shelf life (days)        | 150000 |  38.58 |     3.08 | 104.48 |   0.4 | 719.56 |
| pickup window (hours)    | 150000 |  50.42 |    25.95 |  45.86 |   2   | 168    |
| request lead time (days) | 120000 |   7.45 |     7.37 |   3.71 |   0.5 |  14    |

## Status distributions

**FoodDonation**

| status              |   rows |    % |
|:--------------------|-------:|-----:|
| fully_allocated     |  81158 | 54.1 |
| expired             |  65554 | 43.7 |
| cancelled           |   2992 |  2   |
| available           |    167 |  0.1 |
| partially_allocated |    129 |  0.1 |

**RecipientRequest**

| status              |   rows |    % |
|:--------------------|-------:|-----:|
| fulfilled           |  46718 | 38.9 |
| expired             |  35442 | 29.5 |
| partially_fulfilled |  34485 | 28.7 |
| cancelled           |   2465 |  2.1 |
| open                |    890 |  0.7 |

**Allocation**

| status    |   rows |    % |
|:----------|-------:|-----:|
| delivered | 188378 | 94.9 |
| cancelled |   9788 |  4.9 |
| confirmed |    191 |  0.1 |
| picked_up |     32 |  0   |
| pending   |     26 |  0   |

**Organization**

|                           |   rows |
|:--------------------------|-------:|
| ('both', 'active')        |     28 |
| ('both', 'inactive')      |      7 |
| ('donor', 'active')       |    483 |
| ('donor', 'inactive')     |     16 |
| ('recipient', 'active')   |    452 |
| ('recipient', 'inactive') |     14 |

## Redistribution overview

| metric                                    |      value |
|:------------------------------------------|-----------:|
| servings donated                          |  9,482,989 |
| servings requested                        | 13,630,435 |
| servings allocated (non-cancelled)        |  6,380,567 |
| servings delivered                        |  6,370,644 |
| % of donated servings delivered           |       67.2 |
| % of requested servings delivered         |       46.7 |
| servings lost in expired donations        |  2,896,626 |
| donations never allocated                 |     48,009 |
| allocations per donation (allocated ones) |       1.85 |

## By food category (servings)

| category_id                |         donated |        requested |   delivered |   fill rate % |
|:---------------------------|----------------:|-----------------:|------------:|--------------:|
| Fresh Vegetables           | 705491          |      1.22121e+06 |      673000 |          55.1 |
| Rice, Pasta & Grains       | 251569          |      1.14388e+06 |      245547 |          21.5 |
| Fresh Fruit                | 710158          |      1.08305e+06 |      675132 |          62.3 |
| Canned Fruits & Vegetables | 358901          | 999184           |      347522 |          34.8 |
| Milk                       | 315533          | 926100           |      306236 |          33.1 |
| Canned Proteins & Beans    | 284020          | 922610           |      275174 |          29.8 |
| Prepared Hot Meals         |      1.5709e+06 | 859117           |      745838 |          86.8 |
| Bread & Rolls              | 833812          | 845052           |      564841 |          66.8 |
| Breakfast Cereal           | 232761          | 760339           |      227297 |          29.9 |
| Frozen Meat & Poultry      | 164924          | 723349           |      160545 |          22.2 |
| Eggs                       | 225961          | 607370           |      221067 |          36.4 |
| Soups & Broths             | 181149          | 511109           |      172417 |          33.7 |
| Baby Food & Formula        | 101549          | 491526           |       97513 |          19.8 |
| Frozen Meals               | 215388          | 366598           |      199028 |          54.3 |
| Cheese & Yogurt            | 202586          | 365945           |      194279 |          53.1 |
| Frozen Fruits & Vegetables | 142658          | 323861           |      131376 |          40.6 |
| Sandwiches & Wraps         | 609625          | 309901           |      261995 |          84.5 |
| Fresh Meat & Poultry       | 180233          | 237750           |      127133 |          53.5 |
| Snacks                     | 226171          | 204522           |      163991 |          80.2 |
| Beverages & Juices         | 283389          | 198438           |      174207 |          87.8 |
| Condiments, Sauces & Oils  | 118726          | 198247           |      102824 |          51.9 |
| Salads                     | 480919          | 155219           |      138685 |          89.3 |
| Deli & Prepared Proteins   | 298480          | 129995           |      124095 |          95.5 |
| Pastries & Desserts        | 733564          |  31268           |       30806 |          98.5 |
| Fresh Seafood              |  54522          |  14796           |       10096 |          68.2 |

## Monthly volume (rows)

|         |   donations |   requests |   allocations |
|:--------|------------:|-----------:|--------------:|
| 2025-01 |         288 |        669 |           275 |
| 2025-02 |         664 |       1391 |           858 |
| 2025-03 |        1451 |       1732 |          1956 |
| 2025-04 |        2388 |       2328 |          3244 |
| 2025-05 |        3158 |       2988 |          4185 |
| 2025-06 |        3730 |       3987 |          5092 |
| 2025-07 |        4622 |       4810 |          6335 |
| 2025-08 |        5501 |       5040 |          7657 |
| 2025-09 |        5855 |       4695 |          7517 |
| 2025-10 |        6850 |       5171 |          9080 |
| 2025-11 |        8351 |       5139 |          9789 |
| 2025-12 |       10032 |       7379 |         13044 |
| 2026-01 |        8770 |       7355 |         11841 |
| 2026-02 |        7856 |       6821 |         10891 |
| 2026-03 |        8871 |       6493 |         11948 |
| 2026-04 |        8850 |       6284 |         11396 |
| 2026-05 |        9487 |       6407 |         12346 |
| 2026-06 |        9270 |       7618 |         12347 |
| 2026-07 |        9968 |       8231 |         13379 |
| 2026-08 |       10179 |       8113 |         13546 |
| 2026-09 |       10048 |       7412 |         13722 |
| 2026-10 |       10722 |       7549 |         14042 |
| 2026-11 |        3089 |       2388 |          3925 |

## Validation checks

| check                                            |   violations |
|:-------------------------------------------------|-------------:|
| Organization: PK unique & not null               |            0 |
| FoodCategory: PK unique & not null               |            0 |
| FoodDonation: PK unique & not null               |            0 |
| RecipientRequest: PK unique & not null           |            0 |
| Allocation: PK unique & not null                 |            0 |
| FoodCategory: category_name unique               |            0 |
| Organization: name not null                      |            0 |
| Organization: type in (donor,recipient,both)     |            0 |
| Organization: status in (active,inactive)        |            0 |
| Organization: name <= 150 chars                  |            0 |
| Organization: contact <= 100 chars               |            0 |
| Organization: zip <= 15 chars                    |            0 |
| FoodCategory: storage_type valid                 |            0 |
| FoodDonation: quantity > 0                       |            0 |
| FoodDonation: expires_at > donated_at            |            0 |
| FoodDonation: pickup_deadline >= donated_at      |            0 |
| FoodDonation: status valid                       |            0 |
| RecipientRequest: requested_quantity > 0         |            0 |
| RecipientRequest: needed_by >= requested_at      |            0 |
| RecipientRequest: status valid                   |            0 |
| Allocation: quantity_allocated > 0               |            0 |
| Allocation: status valid                         |            0 |
| Allocation: delivered_at implies picked_up_at    |            0 |
| FK FoodDonation.donor_org_id                     |            0 |
| FK FoodDonation.category_id                      |            0 |
| FK RecipientRequest.recipient_org_id             |            0 |
| FK RecipientRequest.category_id                  |            0 |
| FK Allocation.donation_id                        |            0 |
| FK Allocation.request_id                         |            0 |
| Donor org is donor/both                          |            0 |
| Recipient org is recipient/both                  |            0 |
| Active allocations <= donation quantity          |            0 |
| Active allocations <= requested quantity         |            0 |
| Allocation category: donation = request          |            0 |
| allocated_at >= donated_at and >= requested_at   |            0 |
| allocated_at <= pickup_deadline and <= needed_by |            0 |
| picked_up_at in [allocated_at, pickup_deadline]  |            0 |
| delivered_at > picked_up_at                      |            0 |
| Delivered rows have both timestamps              |            0 |
| No event after snapshot time                     |            0 |
| Cancelled donations/requests have no allocations |            0 |