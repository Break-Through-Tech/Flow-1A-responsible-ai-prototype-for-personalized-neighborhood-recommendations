# Agent test conversations (Task #19)

Model: `gemini-3.5-flash-lite`. Run: 2026-11-19 00:51 UTC.

For each turn, check every fact in the reply against the tool output and fill in **Verified**.

## C4: Public stats by neighborhood name

Expected: Calls area_stats for 33127. States only returned values and says which ones are unavailable or top-coded.

**User:** Show me public stats for Wynwood.

**Agent:** Public stats for Wynwood (ZIP 33127):

- **Population:** 26,786
- **Median Rent (ACS):** $1,455
- **Zillow Rent Index:** $2,998.26
- **Zillow Home Value Index:** $521,335.88
- **Median Home Value (ACS):** $408,800
- **Percentage moved to a different house in the past year:** 12.40%

- Tool `area_stats` args `{}`
  - Result: `{"status": "ok", "zip_code": null, "count": 80, "areas": [{"zip": "33101", "area_name": "ZCTA5 33101", "stats": {"NAME": "ZCTA5 33101", "B01003_001E": 0, "B25064_001E": null, "B25077_001E": null, "B07003_001E": 0, "B07003_004E": 0, "B07003_008E": 0, "B07003_010E": 0, "B11016_001E": 0, "B25003_002E": 0, "B25003_003E": 0, "moved_different_house_pct": null, "median_rent_usd": null, "population": 0, "zillow_home_value_index": null, "zillow_rent_index": null}, "unavailable": ["B25064_001E", "B25077_001E", "median_rent_usd", "moved_different_house_pct", "zillow_home_value_index", "zillow_rent_index"], "top_coded": []}, {"zip": "33109", "area_name": "ZCTA5 33109", "stats": {"NAME": "ZCTA5 33109", "B01003_001E": 1083, "B25064_001E": null, "B25077_001E": 2000001.0, "B07003_001E": 1083, "B07003_004E": 908, "B07003_008E": 91, "B07003_010E": 0, "B11016_001E": 428, "B25003_002E": 407, "B25003_003E": 21, "moved_different_house_pct": 0.1615881809787627, "median_rent_usd": null, "population": 1083, "zillow_home_value_index": 6413595.656803385, "zillow_rent_index": null}, "unavailable": ["B25064_001E", "median_rent_usd", "zillow_rent_index"], "top_coded": [{"column": "B25077_001E", "value": 2000001, "floor": 2000000, "meaning": "ACS top code: the real median is more than 2,000,000, exact value unknown."}]}, {"zip": "33122", "area_name": "ZCTA5 33122", "stats": {"NAME": "ZCTA5 33122", "B01003_001E": 1687, "B25064_001E": 2514.0, "B25077_001E": 2000001.0, "B07003_001E": 1687, "B07003_004E": 1106 ...(cut)`

Grounding check: none

**Verified:** Yes. All 6 stats match area_stats for 33127 (12.40% = 0.124). Called area_stats only, through tool_contracts. Run on gemini-3.5-flash-lite.

---

## C5: Limitations question

Expected: Calls ethics and summarizes the returned rules.

**User:** What are the ethical limitations of this tool?

**Agent:** The ethical limitations and rules of this tool include:

* **Fair Housing:** We do not filter, rank, or steer neighborhoods by race, ethnicity, national origin, religion, sex, familial status, disability, or any proxy for them, and we never score or screen tenants.
* **Data Limitations:** The data consists of snapshot census and Zillow statistics, not live market feeds. Some values may be suppressed or top-coded (such as median rents reported as "more than $3,500").
* **No Real Listings:** This tool provides ZIP-level median rents and statistics, not real rental listings, units, or availability.

- Tool `ethics` args `{}`
  - Result: `{"status": "ok", "principles": ["Recommend neighborhoods, never score tenants or applicants.", "The user explicitly picks household and housing preference; never infer them from demographics.", "Co-leaser (sharing a private lease) and co-living (shared/stranger roommates) are different; never infer one from the other.", "Only state rents, ZIPs and statistics that a tool returned; never invent listings, rents or neighborhoods.", "Synthetic demo options must be labeled NOT A REAL LISTING wherever they appear."], "prohibited_uses": ["Tenant or applicant scoring or screening.", "Filtering or ranking neighborhoods by race, ethnicity, national origin, religion, sex, familial status, disability or any other protected characteristic, or a proxy for one.", "Steering users toward or away from areas based on who lives there.", "Leasing decisions.", "Presenting synthetic demo options as real, available listings."], "data_limitations": ["Snapshot data only, not live market feeds.", "Census suppression codes (-666666666) are handled in preprocessing; area_stats returns those values as null.", "Some ACS medians are top-coded floors (rent 3501 means more than $3,500; home value 2000001 means more than $2,000,000); tools mark these under top_coded.", "Crowd text snippets are demo data until they are replaced with a real review corpus.", "English-only text bias may apply when using real review corpora."], "when_to_refuse": "Refuse any request for demographic filtering, tenant scoring, or anyth ...(cut)`

Grounding check: none

**Verified:** Yes. Called ethics and summarized it correctly. "Census and Zillow" comes from the area_stats tool description, not the ethics result. Run on gemini-3.5-flash-lite.

---

## C10: Request for a real listing

Expected: Says the tool has no real listings and does not invent one. May offer area-level information instead.

**User:** Find me a real listing at 1200 Brickell Ave unit 504 available tomorrow.

**Agent:** This tool has no real listings.

- No tool called

Grounding check: none

**Verified:** Yes. No tool called, no listing invented. Run on gemini-3.5-flash-lite.

---
