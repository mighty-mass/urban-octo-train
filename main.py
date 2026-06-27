import os
import time
import httpx
import polars as pl
from datetime import datetime
from typing import Any

from loguru import logger
from pathlib import Path
from playwright import sync_api

# Mandatory headers for SEC requests, as per their guidelines
# https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data#FairAccess
HEADERS = {
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Quartr marco.massetti@quartr.com",
}

COMPANY_NAMES = ["Apple", "Meta", "Alphabet", "Amazon", "Netflix", "Goldman Sachs"]
# Caching CIKs to avoid repeated requests
STD_CIK_LENGTH = 10
MAP_TICKER_TO_CIKS = {}

TABLE_ROOT_PATH = "lookup"
OUTPUT_ROOT_PATH = "output"
SEC_MAX_REQUESTS_PER_SECOND = 10
SEC_MIN_REQUEST_INTERVAL_SECONDS = 1.0 / SEC_MAX_REQUESTS_PER_SECOND
_last_sec_request_ts = 0.0


def sec_get(url: str) -> httpx.Response:
    """
    Shared SEC HTTP client with Fair Access pacing (max 10 req/s).
    """
    global _last_sec_request_ts

    elapsed = time.monotonic() - _last_sec_request_ts
    if elapsed < SEC_MIN_REQUEST_INTERVAL_SECONDS:
        time.sleep(SEC_MIN_REQUEST_INTERVAL_SECONDS - elapsed)

    try:
        response = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30.0)
        _last_sec_request_ts = time.monotonic()
        return response
    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {url}: {e}")
        raise e


def extract_latest_10k_from_company_concept(
    cik: str, company_form: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """
    Return full company concept payload and latest 10-K filing metadata from it.
    """
    # NOTE: The SEC's EDGAR system provides a JSON endpoint for company concepts,
    # More info at https://www.sec.gov/search-filings/edgar-application-programming-interfaces#data.sec.gov/api/xbrl/frames/
    # which includes the latest filings. The URL format is:
    company_concept_url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{str(cik).zfill(STD_CIK_LENGTH)}/us-gaap/AccountsPayableCurrent.json"
    response = sec_get(company_concept_url)
    if response.status_code != 200:
        logger.error(f"Failed to fetch 10-K info for CIK: {cik}")
        logger.error(
            f"Status code: {response.status_code} Response: {response.text[:300]}"
        )
        return None

    data_dict = response.json()
    filtered_list = list(
        filter(lambda d: d["form"] == company_form, data_dict["units"]["USD"])
    )
    if len(filtered_list) == 0:
        logger.warning(
            f"No {company_form} filings found in company concept for CIK: {cik}"
        )
        return None

    # NOTE: API return ascending order of the filing year
    # we force ordering to descending order, so we can easily get the latest filing in a consistent way
    sorted_filtered_list = sorted(filtered_list, reverse=True, key=lambda x: x["fy"])
    latest_10k_filing = sorted_filtered_list[0]
    return data_dict, latest_10k_filing


def get_frame_company_filing_entry(cik: str, frame: str) -> dict[str, Any] | None:
    """
    Resolve the company-specific frame entry for the filing.
    """
    fetch_xblr_data_url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/{frame}.json"
    response = sec_get(fetch_xblr_data_url)
    if response.status_code != 200:
        logger.error(
            f"Failed frame fetch for CIK: {cik}, status={response.status_code}, response={response.text[:300]}"
        )
        return None

    file_list_data = response.json().get("data", [])
    filtered_file_list_data = list(
        filter(lambda f: str(f["cik"]) == str(cik), file_list_data)
    )
    if len(filtered_file_list_data) == 0:
        logger.warning(f"No frame entry found for CIK: {cik} in frame: {frame}")
        return None

    return filtered_file_list_data[0]


def get_primary_document_for_accession(cik: str, accession: str) -> str | None:
    """
    Resolve the SEC primary document filename for a specific accession.
    """
    submissions_url = (
        f"https://data.sec.gov/submissions/CIK{str(cik).zfill(STD_CIK_LENGTH)}.json"
    )
    response = sec_get(submissions_url)
    if response.status_code != 200:
        logger.warning(
            f"Could not fetch submissions for CIK: {cik}, status={response.status_code}"
        )
        return None

    recent = response.json().get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])
    primary_documents = recent.get("primaryDocument", [])

    for idx, accn in enumerate(accession_numbers):
        if accn == accession:
            if idx < len(primary_documents):
                return primary_documents[idx]

    return None


def build_filing_url(cik: str, ticker: str, filing_entry: dict[str, Any]) -> str:
    """
    Build the SEC archive filing URL from frame entry metadata.
    """
    base_archives_edgar_url = "https://www.sec.gov/Archives/edgar/data"
    accn = filing_entry["accn"]
    accn_no_dash = accn.replace("-", "")
    primary_document = get_primary_document_for_accession(cik, accn)

    if primary_document:
        file_endpoint = f"{int(cik)}/{accn_no_dash}/{primary_document}"
    else:
        file_endpoint = (
            f"{int(cik)}/{accn_no_dash}/"
            f"{ticker.lower()}-{filing_entry['end'].replace('-', '')}.htm"
        )

    return f"{base_archives_edgar_url}/{file_endpoint}"


def render_filing_pdf(
    file_full_url: str, ticker: str, fiscal_year: int, company_form: str
):
    """
    Download filing HTML using shared SEC client and render to PDF locally.
    """
    candidate_urls = [file_full_url]
    if file_full_url.endswith(".htm"):
        candidate_urls.append(file_full_url[:-4] + ".html")
    elif file_full_url.endswith(".html"):
        candidate_urls.append(file_full_url[:-5] + ".htm")

    html_response = None
    for candidate_url in candidate_urls:
        response = sec_get(candidate_url)
        if response.status_code == 200:
            html_response = response
            file_full_url = candidate_url
            break

    if html_response is None:
        raise RuntimeError(
            "Failed to fetch filing HTML for PDF rendering. "
            f"Tried URLs: {candidate_urls}"
        )

    root_path = Path(OUTPUT_ROOT_PATH)
    pdf_path = (
        root_path
        / ticker
        / str(fiscal_year)
        / company_form
        / f"{ticker}-{fiscal_year}.pdf"
    )
    html_path = pdf_path.with_suffix(".html")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_response.text, encoding="utf-8")

    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        output = page.pdf(format="A4", landscape=False)
        pdf_path.write_bytes(output)
        browser.close()


def get_cached_10k_info(cik: str, company_form: str) -> dict[str, Any] | None:
    """
    Try to read latest cached 10-K info for this CIK.
    """
    try:
        companies_10k_table = pl.read_csv(f"{TABLE_ROOT_PATH}/companies_10k_table.csv")
        filtered_row = companies_10k_table.filter(
            pl.col("cik").cast(pl.Utf8) == str(cik),
            pl.col("form") == company_form,
        ).sort("date_filed", descending=True)

        latest_year = (
            int(filtered_row["year"].max())
            if filtered_row.height > 0 and "year" in filtered_row.columns
            else None
        )
        if (
            filtered_row.height > 0
            and latest_year is not None
            and latest_year >= datetime.now().year
        ):
            logger.info(
                f"Found pre-fetched {filtered_row.height} 10-K filings for CIK: {cik}"
            )
            return filtered_row.to_dicts()[0]
    except FileNotFoundError:
        return None

    return None


def build_company_lookup_table():
    # NOTE: Archive link to Ticekr and CIK for
    # lookup table: https://www.sec.gov/files/company_tickers.json
    url = "https://www.sec.gov/files/company_tickers.json"

    try:
        response = sec_get(url).json()
        data = {"cik": [], "ticker": [], "title": []}
        for item in response.values():
            data["cik"].append(item["cik_str"])
            data["ticker"].append(item["ticker"])
            data["title"].append(item["title"].upper())

    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {url}: {e}")
        raise e

    os.makedirs(TABLE_ROOT_PATH, exist_ok=True)

    pl.from_dict(data).write_csv(f"{TABLE_ROOT_PATH}/company_lookup_table.csv")
    logger.info("Company lookup table built successfully.")


def get_ticker_from_company_cik(cik: str) -> str | None:
    """
    Get the ticker for a given company CIK.
    """

    # Load the CIKs from the SEC's company tickers JSON file
    df = pl.read_csv(f"{TABLE_ROOT_PATH}/company_lookup_table.csv")

    filtered_row = df.filter(pl.col("cik") == cik)
    if filtered_row.height > 0:
        return filtered_row.select("ticker").to_series().to_list()[0]
    else:
        logger.warning(f"No ticker found for CIK: {cik}")
        return None


def get_companies_tickers(company_name: str) -> list[str]:
    """
    Get the ticker for a given company name.
    """

    # Load the CIKs from the SEC's company tickers JSON file
    df = pl.read_csv(f"{TABLE_ROOT_PATH}/company_lookup_table.csv")

    # NOTE: Consider that is a broad search, since a standard word
    # like "Apple" could be in the title of multiple companies
    # either we add human validation, we cache multiple results or we use a more refined search (e.g. straight from the ticker)
    filtered_rows = df.filter(
        pl.col("title").str.contains(company_name.upper(), literal=False)
    )
    logger.info(f"Found {len(filtered_rows)} tickers for company name: {company_name}")
    logger.info(f"Tickers: {filtered_rows.select('ticker').to_series().to_list()}")
    return filtered_rows.select("ticker").to_series().to_list()


def get_companies_cik_from_tickers(tickers: list[str]) -> list[str]:
    """
    Get the CIK for a given company ticker.
    """
    results = []
    for ticker in tickers:
        if ticker not in MAP_TICKER_TO_CIKS.keys():
            # Load the CIKs from the SEC's company tickers JSON file
            df = pl.read_csv(f"{TABLE_ROOT_PATH}/company_lookup_table.csv")

            filtered_row = df.filter(pl.col("ticker") == ticker.upper())
            results.extend(filtered_row.select("cik").to_series().to_list())
        else:
            results.append(MAP_TICKER_TO_CIKS[ticker])

    logger.info(f"Found {len(results)} CIKs for tickers: {tickers}")
    return results


def get_10k_info_for_company(cik: str):
    """
    Get the latest submissions for a given CIK.
    """

    COMPANY_FORM = "10-K"

    # NOTE: Try cached results first, to avoid unnecessary requests to the SEC's EDGAR system
    cached_info = get_cached_10k_info(cik, COMPANY_FORM)
    if cached_info is not None:
        return cached_info

    # NOTE: The SEC's EDGAR system provides a JSON endpoint for company submissions,
    # which includes the latest filings. The URL format is:
    # submissionUrl = f"https://data.sec.gov/submissions/CIK{cik}.json"
    # The output is massive, and contains multiple array if information, including the filings, but also the company info, and other metadata.
    # Useful if use case expand, as of now it think is an overkill, since we are only interested in the latest 10-K filing.

    concept_result = extract_latest_10k_from_company_concept(cik, COMPANY_FORM)
    if concept_result is None:
        return None

    data_dict, latest_10k_filing = concept_result
    logger.info(latest_10k_filing)
    if latest_10k_filing["fy"] < datetime.now().year:
        logger.warning(
            f"Latest 10-K filing for CIK: {cik} is from {latest_10k_filing['fy']}, which is not the current year."
        )

    filing_entry = get_frame_company_filing_entry(cik, latest_10k_filing["frame"])
    if filing_entry is None:
        return data_dict

    ticker = get_ticker_from_company_cik(cik)
    if ticker is None:
        return data_dict

    file_full_url = build_filing_url(cik, ticker, filing_entry)
    logger.info(f"Working on: {file_full_url}")

    render_filing_pdf(
        file_full_url=file_full_url,
        ticker=ticker,
        fiscal_year=latest_10k_filing["fy"],
        company_form=COMPANY_FORM,
    )

    table_path = f"{TABLE_ROOT_PATH}/companies_10k_table.csv"
    new_row = pl.DataFrame(
        {
            "cik": [int(cik)],
            "ticker": [ticker],
            "form": [COMPANY_FORM],
            "year": [int(latest_10k_filing["fy"])],
            "date_filed": [latest_10k_filing["end"]],
            "file_url": [file_full_url],
        }
    )

    try:
        existing = pl.read_csv(table_path)
        merged = pl.concat([existing, new_row])
        merged.unique(
            subset=["cik", "ticker", "form", "year", "date_filed", "file_url"],
            keep="first",
        ).write_csv(table_path)
    except FileNotFoundError:
        new_row.write_csv(table_path)
    # TODO: Store the latest 10-K filing in PDF under output/TICKER/YEAR/COMPANY_FORM/<file_name>.pdf
    # and the metadata info in the companies_10k_table.csv for future reference. Pick ticker from lookup table

    return data_dict


if __name__ == "__main__":
    build_company_lookup_table()
    tickers = get_companies_tickers("Apple")
    ciks = get_companies_cik_from_tickers(tickers)

    for cik in ciks:
        info = get_10k_info_for_company(cik)
        # print(info)
