# Orange County source-of-record matrix

Recon date: 2026-07-16  
Build status: `PARTIAL_BUILD_READY`

| Lead or enrichment type | Source | Status | Evidence / limitation |
| --- | --- | --- | --- |
| Recorded instruments | `clerk_recordings` | Live primary | Orange County Comptroller Official Records page links to the public records search and lists deeds, mortgages, liens, satisfactions, and final judgments. |
| Civil and foreclosure cases | `court_civil` | Live supporting | MyEClerk exposes public case search; document availability varies by case type and date. |
| Foreclosure sales | `foreclosure_sales` | Live primary | Official Clerk homepage links to the RealForeclose auction portal. |
| Tax deed sales | `tax_deed_sales` | Live primary, limited | Official Comptroller page links to Tax Deed Sales; adapter-level search verification remains Build Mode work. |
| Code enforcement | `code_enforcement` | Live primary, limited | Official Code Compliance page links to the open violation search; recorded liens remain Official Records events. |
| Parcel enrichment | `parcel_master` | Live enrichment | Official Property Appraiser search supports owner, address, sales, and property-use lookup. |
| GIS enrichment | `gis_parcels` | Live enrichment | Official GIS page links to public InfoMap/data; a public ArcGIS parcel layer was confirmed. |
| Parcel-level tax delinquency | `tax_collector` | Blocked | Official Tax Collector documentation confirms delinquency and certificate-sale process, but no public parcel-level list or bulk file was verified. |

No enrichment source may create a lead row by itself.
