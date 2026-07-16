# Orange County source coverage map

## Live sources

- `clerk_recordings` — primary daily event source
- `foreclosure_sales` — primary foreclosure-sale event source
- `court_civil` — supporting public court search
- `tax_deed_sales` — primary tax-deed event source, limited coverage pending adapter proof
- `code_enforcement` — primary open-violation event source, limited coverage
- `parcel_master` — enrichment only
- `gis_parcels` — enrichment only

## Blocked or operator-review sources

- `tax_collector` — no verified public parcel-level delinquency feed; next strategy is a final public-records request path if the operator wants this source.

## Gate result

The P0 gate is satisfied by official recorded instruments and the officially linked foreclosure-sales portal. The build remains `READY_WITH_BLOCKERS` because parcel-level tax delinquency access is unresolved and several sources require adapter-level proof.
