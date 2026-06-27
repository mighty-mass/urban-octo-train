# Project Context Summary

## Goal
This script fetches SEC filing metadata for companies, identifies recent 10-K information, and renders filing HTML into PDFs under the output folder.

## Main Flow
1. Build local company lookup table from SEC ticker dataset.
2. Resolve ticker list from company name.
3. Resolve CIK(s) from ticker(s).
4. For each CIK, fetch latest 10-K-related concept info from SEC XBRL endpoints.
5. Resolve a company-specific filing entry from the frame endpoint.
6. Build archive filing URL and render the filing as PDF.

## Key Files and Paths
- `main.py`: all runtime logic.
- `lookup/company_lookup_table.csv`: local cache of CIK/ticker/title mapping.
- `lookup/companies_10k_table.csv`: optional cache for previously fetched 10-K metadata.
- `output/<TICKER>/<FY>/10-K/<TICKER>-<FY>.pdf`: generated PDF output.

## Important Constants
- `HEADERS`: SEC request headers with User-Agent and compression.
- `STD_CIK_LENGTH`: CIK normalization length (10 digits).
- `SEC_MAX_REQUESTS_PER_SECOND`: target SEC fair-access limit.

## Refactor Notes
`get_10k_info_for_company` was split into smaller helpers to improve readability while preserving behavior:
- `sec_get(url)`: shared HTTP function for all SEC URL calls with built-in pacing (10 req/s).
- `get_cached_10k_info(cik, company_form)`: reads cached 10-K metadata if present and current.
- `extract_latest_10k_from_company_concept(cik, company_form)`: pulls latest 10-K entry from company concept payload.
- `get_frame_company_filing_entry(cik, frame)`: resolves company-specific frame row.
- `build_filing_url(cik, ticker, filing_entry)`: constructs SEC archive document URL.
- `render_filing_pdf(file_full_url, ticker, fiscal_year, company_form)`: downloads filing HTML and renders local PDF via Playwright.

## Current Assumptions / Limitations
- Filing document URL is derived from ticker + period end naming convention in `build_filing_url`.
- XBRL concept currently anchors on `us-gaap/AccountsPayableCurrent` to discover the latest filing frame.
- Missing local Python dependencies (`httpx`, `polars`, `loguru`, `playwright`) in current editor environment may show diagnostics even if code structure is correct.

## Suggested Next Improvements
- Resolve filing URL via `submissions` API (`primaryDocument`) instead of inferred filename convention.
- Add retry/backoff for transient SEC errors (403/429/5xx).
- Persist normalized 10-K metadata to `lookup/companies_10k_table.csv` after successful fetch.
