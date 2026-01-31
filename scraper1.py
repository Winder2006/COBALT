import argparse
import json
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

def extract_document_metadata(url: str) -> dict:
    """Scrape document metadata from the given RR BOTW activity detail page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the page and wait for all AJAX content to finish loading
        page.goto(url, wait_until="networkidle")

        # Select all data rows from the table body
        rows = page.query_selector_all("#actionTable tbody tr")

        documents = []

        for row in rows:
            cells = row.query_selector_all("td")

            # Skip malformed rows
            if len(cells) < 4:
                continue

            # ---- Extract download URL from the file column ----
            link_tag = cells[0].query_selector("a")
            href = None
            if link_tag:
                raw_href = link_tag.get_attribute("href")
                if raw_href:
                    href = urljoin(url, raw_href)

            # ---- Extract text fields ----
            category = cells[1].inner_text().strip()
            date = cells[2].inner_text().strip()
            action_code = cells[3].inner_text().strip()
            name = cells[4].inner_text().strip() if len(cells) > 4 else ""
            comment = cells[5].inner_text().strip() if len(cells) > 5 else ""

            documents.append({
                "download_url": href,
                "category": category,
                "date": date,
                "action_code": action_code,
                "name": name,
                "comment": comment,
            })

        browser.close()

        # Return one JSON object containing all documents
        return {"documents": documents}

def build_activity_url(property_id: str) -> str:
    """Return the RR BOTW activity detail URL for the provided property id."""
    base_url = "https://apps.dnr.wi.gov/rrbotw/botw-activity-detail"
    return f"{base_url}?dsn={property_id}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download document metadata for a RR BOTW property.",
    )
    parser.add_argument(
        "--property-id",
        default="588459",
        help="RR BOTW property/DSN identifier (defaults to 588459).",
    )
    parser.add_argument(
        "--output",
        default="output.json",
        help="Destination JSON file for the scraped metadata (defaults to output.json).",
    )
    args = parser.parse_args()

    url = build_activity_url(args.property_id)
    data = extract_document_metadata(url)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"Saved metadata for property {args.property_id} to {args.output}")
