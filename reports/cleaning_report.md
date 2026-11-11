# Synthetic data cleaning & integration report

## 1. Organization registry (synthetic donors / recipients)

* Raw registrations: 687
* Standardised: ZIP formats (71 fixed, e.g. '19103-1234', '19103.0'), status case/whitespace, role case, city spellings (56 fixed: Phila / PHILADELPHIA / 'Philadelphia, PA').
* Entity resolution: 687 registrations -> 654 organisations. Against the injected ground truth: precision 1.000, recall 1.000 (33/33 duplicate pairs found, 0 false merges).

**Organization table: 1000 rows** = 346 real Philadelphia sites (ids 1-346) + 654 synthetic organisations (ids 347-1000).

| organization_type   |   rows |
|:--------------------|-------:|
| donor               |    499 |
| recipient           |    466 |
| both                |     35 |


## 2. FoodDonation cleaning

| step                                                                             |   rows remaining |   removed |
|:---------------------------------------------------------------------------------|-----------------:|----------:|
| raw rows                                                                         |           152400 |         0 |
| unknown organisation key removed                                                 |           151800 |       600 |
| organisation not a valid donor removed                                           |           151800 |         0 |
| unmapped category label removed (4283 variant labels standardised)               |           151800 |         0 |
| missing / non-positive quantity removed (2348 '45 servings'-style values parsed) |           151200 |       600 |
| unparseable timestamp removed (2983 MM/DD/YYYY timestamps converted)             |           151200 |         0 |
| expiry before posting / pickup before posting removed                            |           150600 |       600 |
| pickup deadline clamped to expiry (0 rows)                                       |           150600 |         0 |
| duplicate submissions removed (same org, category, quantity, timestamps)         |           150000 |       600 |

## 3. RecipientRequest cleaning

| step                                                                             |   rows remaining |   removed |
|:---------------------------------------------------------------------------------|-----------------:|----------:|
| raw rows                                                                         |           121920 |         0 |
| unknown organisation key removed                                                 |           121440 |       480 |
| organisation not a valid recipient removed                                       |           121440 |         0 |
| unmapped category label removed (2539 variant labels standardised)               |           121440 |         0 |
| missing / non-positive quantity removed (1794 '45 servings'-style values parsed) |           120960 |       480 |
| unparseable timestamp removed (2369 MM/DD/YYYY timestamps converted)             |           120960 |         0 |
| needed-by before request time removed                                            |           120480 |       480 |
| duplicate submissions removed (same org, category, quantity, timestamps)         |           120000 |       480 |