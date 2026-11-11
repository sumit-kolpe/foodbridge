# Philadelphia Free Food & Meal Sites - EDA and cleaning log

Source: City of Philadelphia ArcGIS layer `free_meal_sites` (OpenDataPhilly), exported 2026-11-10.

* Raw file size: 112.7 KB
* Raw shape: 404 rows x 53 columns (51 source attributes + exported lon/lat)

## Categorical distributions (raw)

**category_type**

| category_type     |   rows |
|:------------------|-------:|
| Food Site         |    300 |
| General Meal Site |     51 |
| Senior Meal Site  |     27 |
| Public Benefits   |     26 |

**status**

| status             |   rows |
|:-------------------|-------:|
| Active             |    394 |
| Permanently Closed |     10 |

**category**

| category                             |   rows |
|:-------------------------------------|-------:|
| PHILABUNDANCE                        |    107 |
| Caring for Friends Food Site         |     95 |
| SHARE FOOD PROGRAM                   |     52 |
| Office of Homeless Services          |     42 |
| PCA                                  |     22 |
| Community Refrigerators              |     20 |
| Free Grocery Site                    |     11 |
| WIC                                  |     11 |
| Neighborhood Community Action Center |      9 |
| PHILABUNDANCE/SHARE FOOD PROGRAM     |      6 |
| BenePhilly                           |      6 |
| Small Things Philly                  |      5 |
| PHILABUNDANCE meal                   |      5 |
| PPR_Senior                           |      5 |
| Nutritional Development Services     |      4 |
| Free Meal Site                       |      3 |
| General Food Site                    |      1 |

## Missing values (% of rows) for key fields

|                  |   % missing |
|:-----------------|------------:|
| site_name        |         0   |
| address          |         0   |
| zip_code         |         0.2 |
| phone_number     |        18.6 |
| website          |         4.5 |
| hours_mon_start1 |        81.4 |
| site_key         |        88.4 |
| email            |        99.5 |

* Rows with **no** operating hours at all: 69 (17.1%). Treated as *unknown*, not closed.
* Latitude 39.898 to 40.123 (mean 39.9941, sd 0.0447); longitude -75.252 to -74.976 (mean -75.1533, sd 0.0543)

## Cleaning log

* ZIP codes standardised to 5 digits; 1 row(s) have no recoverable ZIP and keep NULL (not imputed).
* Status mapped: {'active': 394, 'inactive': 10}
* Contact field split: 313 phones and 26 emails extracted (emails were mixed into `phone_number` in the source).
* Entity resolution (block = normalised address, match = name similarity >= 0.6): 404 rows -> 371 organisations; 32 clusters merged 65 rows.

### Merged clusters

|   cluster | names                                                                                                              | addresses                                               | types                                          |
|----------:|:-------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------|:-----------------------------------------------|
|         1 | Mighty Writers West                                                                                                | 3520 Fairmount Ave. | 3520 Fairmount Ave                | Food Site                                      |
|         5 | Kleinlife Northeast & Kleinlife Russian Satellite                                                                  | 10100 Jamison Ave | 10100 Jamison Ave.                  | Food Site, Senior Meal Site                    |
|        23 | Face to Face Germantown                                                                                            | 123 E Price St | 123 E. Price St                        | Food Site, General Meal Site                   |
|        35 | Lutheran Settlement House                                                                                          | 1340 Frankford Ave. | 1340 Frankford Ave                | Food Site, General Meal Site, Senior Meal Site |
|        56 | Bethel Worship Center                                                                                              | 169 W. Wyoming Ave.                                     | Food Site, General Meal Site                   |
|        67 | Germantown Community Fridge                                                                                        | 19 E. High St. | 19 E High St                           | Food Site                                      |
|        70 | Bethel Presbyterian Church                                                                                         | 1900 W York St | 1900 W York St.                        | Food Site, General Meal Site                   |
|        82 | Mi Salud Wellness Center                                                                                           | 200 E. Wyoming Ave. | 200 E Wyoming Ave                 | Food Site                                      |
|        90 | Saint Edmond Senior Community Center | St. Edmonds Senior Community Center Catholic Housing and Community Services | 2130 S 21st St.                                         | Food Site, Senior Meal Site                    |
|        92 | Saint Michael's Lutheran Church | St. Michael's Lutheran Church                                                    | 2139 E Cumberland St | 2139 E Cumberland Street         | Food Site                                      |
|       108 | Whitman Council, Inc | Whitman Council Inc                                                                         | 2455 S. 3rd Street | 2455 S 3rd Street                  | Food Site                                      |
|       110 | Ian-Yae's In Touch | Ian-Yae’s In Touch                                                                            | 2524 N. 27th St. | 2524 N 27th St                       | Food Site, General Meal Site                   |
|       136 | Friends Pantry & Community Fridge                                                                                  | 320 Arch St | 320 Arch Street                           | Food Site                                      |
|       141 | Brothers of Strawberry Mansion                                                                                     | 3218 W Susquehanna Ave | 3218 W Susquehanna Avenue      | Food Site                                      |
|       144 | Philadelphia Masjid                                                                                                | 4700 Wyalusing Ave | 4700 Wyalusing Ave.                | Food Site                                      |
|       149 | Drexel University Dornsife Center for Neighborhood Partnerships                                                    | 3509 Brandywine Street                                  | Food Site, General Meal Site                   |
|       156 | Chosen 300 Ministries Inc. | Chosen 300 West                                                                       | 3959 Lancaster Ave                                      | Food Site, General Meal Site                   |
|       162 | Mizpah SDA                                                                                                         | 4355 Paul St                                            | Food Site                                      |
|       166 | West Philadelphia SDA                                                                                              | 4527 Haverford Ave.                                     | Food Site, General Meal Site                   |
|       170 | Bless Philadelphia Corporation                                                                                     | 4610 Devereaux St                                       | Food Site, General Meal Site                   |
|       176 | Northeast Baptist Church Oasis Food Ministry | Northeast Baptist Church                                            | 4744 Tackawanna St                                      | Food Site                                      |
|       178 | Katie's Cupboard at Tabor | Katie’s Cupboard at Tabor                                                              | 4860 N Howard St | 4860 N Howard street                 | Food Site                                      |
|       188 | Somerton Food Bank | Somerton Interfaith Food Bank                                                                 | 510 Somerton Ave. | 510 Somerton Avenue                 | Food Site                                      |
|       194 | Helping Hands for the Hungry                                                                                       | 525 S. Cobbs Creek Parkway | 525 So Cobbs Creek Parkway | Food Site, General Meal Site                   |
|       221 | Episcopal Community Services | Episcopal Community Service St. Barnabas Community Resource Center                  | 6006 W Girard Ave | 6006 West Girard Ave                | Food Site                                      |
|       233 | Breaking Bread on Broad | Rodeph Shalom Breaking Bread on Broad                                                    | 615 N Broad St                                          | Food Site                                      |
|       236 | Catholic Social Services Southwest Family Service Center | BenePhilly Center at Catholic Social Services Southwest | 6214 Grays Ave | 6214 Grays Ave.                        | Food Site, Public Benefits                     |
|       239 | Kingdom Life Christian Center                                                                                      | 6325 Frankford Ave. | 6325 Frankford Ave                | Food Site                                      |
|       265 | St Paul A.M.E. Church | St. Paul                                                                                   | 8398 Lindbergh Blvd                                     | Food Site                                      |
|       268 | Bethany AME Church | Bethany A. M. E. Church                                                                       | 8898 Ashton Rd | 8898 Ashton Road                       | Food Site                                      |
|       269 | Our Brother's Place | Our Brother's Place (Bethesda Project)                                                       | 907 Hamilton St. | 907 Hamilton St                      | Food Site, General Meal Site                   |
|       286 | Bread of Life | Keeping It Real Christian Fellowship Bread of Life Ministry                                        | North 17th St. and Benjamin Franklin Parkway            | General Meal Site                              |

### ZIP conflicts resolved (nearest ZIP centroid to site coordinates)

* Ian-Yae's In Touch (2524 N. 27th St.): ['19132', '19145'] -> 19132 (record geocoded on the wrong side of Market St discarded)

* Removed 25 public-benefits-only organisations (they do not receive food donations).
* **Final: 346 recipient organisations** (338 active, 8 inactive).

Final service-type mix:

| service_types                                |   orgs |
|:---------------------------------------------|-------:|
| Food Site                                    |    269 |
| General Meal Site                            |     39 |
| Senior Meal Site                             |     24 |
| Food Site;General Meal Site                  |     10 |
| Food Site;Senior Meal Site                   |      2 |
| Food Site;General Meal Site;Senior Meal Site |      1 |
| Food Site;Public Benefits                    |      1 |