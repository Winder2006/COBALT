"""
Real BRRTS client with live scraping from Wisconsin DNR.

This pulls:
- Site information
- Risk flags (inferred)
- Summary placeholder
- ALL document links under the BRRTS ID
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://apps.dnr.wi.gov"
DETAIL_PATH = "/apps/brtsonline/Details.aspx?id="


def fetch_site_data(brrts_id: str) -> dict:
    """
    Scrapes real Wisconsin DNR BRRTS site + document data.
    """

    url = BASE_URL + DETAIL_PATH + str(brrts_id)

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        return {
            "site_info": {
                "dsn": brrts_id,
                "activity_number": "ERROR",
                "status": "UNAVAILABLE",
                "activity_type": "UNAVAILABLE",
                "location_name": "Could not reach DNR site",
                "address": "N/A",
                "municipality": "N/A",
                "county": "N/A",
                "dnr_region": "N/A",
                "start_date": "N/A",
                "end_date": "N/A",
            },
            "risk_flags": {
                "status_label": "UNKNOWN",
                "pfas": False,
                "petroleum": False,
                "heavy_metals": False,
                "offsite_impact": False,
            },
            "summary": "Unable to connect to Wisconsin DNR BRRTS system.",
            "documents": [],
        }

    soup = BeautifulSoup(response.text, "html.parser")

    def get_text(label):
        cell = soup.find("td", string=label)
        if cell:
            value = cell.find_next_sibling("td")
            return value.text.strip()
        return "Not available"

    site_info = {
        "dsn": brrts_id,
        "activity_number": get_text("Activity Number"),
        "status": get_text("Status"),
        "activity_type": get_text("Activity Type"),
        "location_name": get_text("Location Name"),
        "address": get_text("Address"),
        "municipality": get_text("Municipality"),
        "county": get_text("County"),
        "dnr_region": get_text("DNR Region"),
        "start_date": get_text("Start Date"),
        "end_date": get_text("End Date"),
    }

    # --- SIMPLE RISK INFERENCE (can be upgraded later)
    status_text = site_info["status"].upper()

    risk_flags = {
        "status_label": status_text,
        "pfas": "PFAS" in response.text,
        "petroleum": "PETROLEUM" in response.text or "LUST" in response.text,
        "heavy_metals": "METAL" in response.text,
        "offsite_impact": "OFFSITE" in response.text,
    }

    # --- SCRAPE DOCUMENTS
    documents = []
    doc_table = soup.find("table", {"id": "ctl00_ContentPlaceHolder1_grdDocuments"})

    if doc_table:
        rows = doc_table.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                title = cols[0].text.strip()
                date = cols[1].text.strip()
                link_tag = cols[2].find("a")
                if link_tag:
                    doc_url = urljoin(BASE_URL, link_tag["href"])
                else:
                    doc_url = None

                documents.append({
                    "title": title,
                    "date": date,
                    "url": doc_url,
                })

    summary = (
        "This summary is generated from publicly available Wisconsin DNR BRRTS data.\n\n"
        "1. Regulatory Status\n"
        f"- Current status is listed as: {site_info['status']}.\n\n"
        "2. Environmental Risk Indicators\n"
        "- Petroleum, metals, or PFAS may be present depending on site history.\n\n"
        "3. Advisory\n"
        "- Always review original reports and closure letters for legal decisions.\n"
        "- Phase I/II ESA review is recommended for acquisition.\n"
    )

    return {
        "site_info": site_info,
        "risk_flags": risk_flags,
        "summary": summary,
        "documents": documents,
    }
