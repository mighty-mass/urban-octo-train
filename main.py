import os
import httpx
import polars as pl
from datetime import datetime

from loguru import logger

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


def build_company_lookup_table():
    # NOTE: Archive link to Ticekr and CIK for
    # lookup table: https://www.sec.gov/files/company_tickers.json
    url = "https://www.sec.gov/files/company_tickers.json"

    try:
        response = httpx.get(url, headers=HEADERS).json()
        data = {"cik_str": [], "ticker": [], "title": []}
        for item in response.values():
            data["cik_str"].append(item["cik_str"])
            data["ticker"].append(item["ticker"])
            data["title"].append(item["title"].upper())

    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {url}: {e}")
        raise e

    os.makedirs(TABLE_ROOT_PATH, exist_ok=True)

    pl.from_dict(data).write_csv(f"{TABLE_ROOT_PATH}/company_lookup_table.csv")
    logger.info("Company lookup table built successfully.")


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
            results.extend(filtered_row.select("cik_str").to_series().to_list())
        else:
            results.append(MAP_TICKER_TO_CIKS[ticker])

    logger.info(f"Found {len(results)} CIKs for tickers: {tickers}")
    return results


def get_10k_info_for_company(cik: str):
    """
    Get the latest submissions for a given CIK.
    """

    COMPANY_FORM = "10-K"
    try:
        companies_10k_table = pl.read_csv(f"{TABLE_ROOT_PATH}/companies_10k_table.csv")
        filtered_row = companies_10k_table.filter(
            pl.col("cik") == cik,
            pl.col("form") == COMPANY_FORM,
            order_by=pl.col("date_filed").desc(),
        )
        if (
            filtered_row.height > 0
            and filtered_row["date_filed"].max().year >= datetime.now().year
        ):
            # NOTE: the 10-k should be annual, so we can assume that if
            # the latest 10-k is already in the table, we don't need to fetch it again
            # Question: can happen that a company files multiple 10-Ks in the same year? Or a file is amended?
            logger.info(
                f"Found pre-fetched {filtered_row.height} 10-K filings for CIK: {cik}"
            )
            return filtered_row.to_dicts()[0]
    except FileNotFoundError:
        pass

    # NOTE: The SEC's EDGAR system provides a JSON endpoint for company submissions,
    # which includes the latest filings. The URL format is:
    # submissionUrl = f"https://data.sec.gov/submissions/CIK{cik}.json"
    # The output is massive, and contains multiple array if information, including the filings, but also the company info, and other metadata.
    # Useful if use case expand, as of now it think is an overkill, since we are only interested in the latest 10-K filing.

    # NOTE: The SEC's EDGAR system provides a JSON endpoint for company concepts,
    # More info at https://www.sec.gov/search-filings/edgar-application-programming-interfaces#data.sec.gov/api/xbrl/frames/
    # which includes the latest filings. The URL format is:
    companyConceptUrl = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/AccountsPayableCurrent.json"
    try:
        response = httpx.get(companyConceptUrl, headers=HEADERS)
        if response.status_code == 200:
            data_dict = response.json()

            # NOTE: API return ascending order of the filing year
            # we force ordering to descending order, so we can easily get the latest filing in a consistent way
            filtered_list = list(
                filter(lambda d: d["form"] == COMPANY_FORM, data_dict["units"]["USD"])
            )
            sorted_filtered_list = sorted(
                filtered_list,
                reverse=True,
                key=lambda x: x["fy"],
            )

            latest_10k_filing = sorted_filtered_list[0]
            logger.info(latest_10k_filing)
            if latest_10k_filing["fy"] < datetime.now().year:
                logger.warning(
                    f"Latest 10-K filing for CIK: {cik} is from {latest_10k_filing['fy']}, which is not the current year."
                )

            https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/{latest_10k_filing['frame']}.json

            # TODO: Fetch the xbrl frame for the latest 10-K filing

            # TODO: Store the latest 10-K filing in PDF under output/TICKER/YEAR/COMPANY_FORM/<file_name>.pdf 
            # and the metadata info in the companies_10k_table.csv for future reference. Pick ticker from lookup table

            
        
            return data_dict
        else:
            logger.error(f"Failed to fetch 10-K info for CIK: {cik}")
            logger.error(
                f"Status code: {response.status_code} Response: {response.text}"
            )
    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {companyConceptUrl}: {e}")
    except Exception as e:
        logger.info(f"Finished fetching 10-K info for CIK: {cik}")


if __name__ == "__main__":
    build_company_lookup_table()
    tickers = get_companies_tickers("Apple")
    ciks = get_companies_cik_from_tickers(tickers)
    std_ciks = [str(cik).zfill(STD_CIK_LENGTH) for cik in ciks]
    print(std_ciks)

    for cik in std_ciks:
        info = get_10k_info_for_company(cik)
        # print(info)
