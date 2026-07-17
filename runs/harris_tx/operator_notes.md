# Operator Notes — Harris County, Texas (Phase 0/1)

## clerk_recordings
- Source: Harris County Clerk Real Property search `RP.aspx`
- Access: public index search, no login required for search
- Confirmed: offline parser works on captured results HTML, yielding lead-eligible rows with file number/date/doc type
- Confirmed: live reliability solved with anti-detection Playwright run; fresh automation can return results when properly configured
- Operator action: none required unless portal behavior changes

## foreclosure_notices_map
- Source: Harris County Tax Assessor-Collector delinquent tax sale listing
- URL: https://www.hctax.net/Property/listings/taxsalelisting
- Access: public listing page, terms-of-use session accepted
- Verified live: fresh run produced 273 actual property rows with Account Number, Cause, Adjudged Value, Minimum Bid, Sale Date, Precinct

## court_civil
- Source: Harris County District Clerk civil/search records
- URL: https://www.hcdistrictclerk.com/Edocs/Public/Search.aspx?Tab=tabCivilMobile
- Confirmed: Playwright login successful with declared free-account credentials
- Confirmed: post-login page remains on `search.aspx`; logout indicator present
- Confirmed blocker: search form controls remain hidden/inaccessible to automation after login; Playwright fill/click blocked by visibility checks
- Operator action: manual operator-assisted pull required — run a party/case search in browser, save the results text/HTML locally, and feed it to the parser

## tax_collector / court_eviction / parcel_master / gis_parcels
- See `config/counties/harris_tx.json` for source states and access strategies
