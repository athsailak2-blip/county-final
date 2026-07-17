# LAUNCH_HARRIS_TX.md

Harris County, Texas county intelligence build package.

## Build state

- Phase 0: COMPLETE
- Config: `config/counties/harris_tx.json`
- Build verdict: `READY_TO_BUILD`
- Status notes: `court_civil` is structurally resolved as `REQUIRES_CREDENTIALS`; operator credentials are recorded in auto_resolve_attempt but not stored in plaintext in repo files.

## Sources

| Source key | Category | Subtype | Role | Verified access |
|---|---|---|---|---|
| clerk_recordings | lead | clerk_recordings | PRIMARY_LEAD_SOURCE | Index search public, documents login/purchase gated |
| foreclosure_notices_map | lead | tax_delinquency | PRIMARY_LEAD_SOURCE | Public TERMS/session gated listing page |
| tax_collector | lead | tax_delinquency | PRIMARY_LEAD_SOURCE | Public account lookup |
| court_civil | lead | court_civil | PRIMARY_LEAD_SOURCE | Login-walled; credentials prepared |
| court_eviction | lead | court_eviction | SUPPORTING_LEAD_SOURCE | Informational; JP portal pending |
| parcel_master | enrichment | parcel_master | ENRICHMENT_SOURCE | Public search blocked at recon; GIS path exists |
| gis_parcels | enrichment | gis_parcels | ENRICHMENT_SOURCE | Public downloads |

## Buy flow decision

RECOMMENDED START: `clerk_recordings` + `foreclosure_notices_map` partial build
- clerk_recordings exposes public search by grantor/grantee/trustee/date/instrument type.
- foreclosure_notices_map exposes tax-sale property rows with address, account/cause numbers, adjudged value, minimum bid, sale date, precinct.

## Next actions for operator

1. Confirm whether to proceed FULL or PARTIAL build.
2. If FULL: inject `court_civil` credentials via the runtime secret path, not via repo config.
3. Confirm tax-sale TOU acceptance workflow for automation.
4. Confirm whether `court_eviction` JP portal discovery is in scope.

## Files

- `config/counties/harris_tx.json` — source of truth county config
- `runs/harris_tx/operator_notes.md` — recon notes and open questions
