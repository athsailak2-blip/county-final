# Orange County API discovery report

Recon checked official Comptroller, Clerk, Code Compliance, Property Appraiser, and GIS navigation pages.

## Confirmed

- Public ArcGIS parcel layer: `https://ocgis4.ocfl.net/arcgis/rest/services/Gridics/MapServer/37`
- Public GIS navigation and downloads: `https://www.ocfl.net/PlanningDevelopment/InteractiveMapping.aspx`

The ArcGIS layer exposes JSON/GeoJSON query capability and parcel attributes. It is enrichment only.

## Deferred to Build Mode

- Network/API fingerprinting for the Comptroller records search
- Network/API fingerprinting for MyEClerk
- Adapter proof for RealForeclose and Tax Deed Sales

No undocumented API endpoint was promoted into the county config.
