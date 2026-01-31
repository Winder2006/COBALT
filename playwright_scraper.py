"""
Playwright Scraper - Runs as a separate process to avoid Flask crashes.
Called via subprocess from the main app.
"""

import sys
import json
import re
from playwright.sync_api import sync_playwright


def scrape_brrts_site(dsn: str) -> dict:
    """
    Scrape all site information from the BRRTS page using Playwright.
    Returns complete site data including documents.
    """
    url = f"https://apps.dnr.wi.gov/rrbotw/botw-activity-detail?dsn={dsn}"
    
    result = {
        "site_info": {"dsn": dsn},
        "risk_flags": {"status_label": "UNKNOWN"},
        "documents": [],
        "error": None
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Load page and wait for content
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)  # Extra wait for AJAX content
            
            site_info = {"dsn": dsn}
            
            # Get activity number and name from header
            page_text = page.inner_text("body")
            header_match = re.search(
                r'(\d{2}-\d{2}-\d+)\s+([A-Z][A-Z0-9\s\'\-\.]+?)(?:\s*Activity Type|\s*$)',
                page_text
            )
            if header_match:
                site_info["activity_number"] = header_match.group(1)
                site_info["location_name"] = header_match.group(2).strip()
            
            # Get all INPUT elements with form-control textbox class - these contain the values
            inputs = page.locator("input.form-control.textbox, INPUT.form-control").all()
            values = []
            for inp in inputs:
                try:
                    val = inp.get_attribute("value") or inp.inner_text() or ""
                    values.append(val.strip())
                except:
                    values.append("")
            
            # Map values by position (0-indexed, first real value at index 0)
            # Based on the debug output:
            # 0: Activity Type (LUST)
            # 1: Status (CLOSED)
            # 2: Jurisdiction (DNR RR)
            # 3: DNR Region (SOUTHEAST)
            # 4: County (MILWAUKEE)
            # 5: Location Name (J CAMP VAN DYKE)
            # 6: Address (3575 N LAKE DR)
            # 7: Municipality (SHOREWOOD)
            # 8: PLSS Description
            # 9: Latitude
            # 10: Longitude
            # 11: Acres
            # 12: Facility ID
            # 13: PECFA Number
            # 14: EPA ID
            # 15: Start Date
            # 16: End Date
            field_positions = {
                0: "activity_type",
                1: "status",
                2: "jurisdiction",
                3: "dnr_region",
                4: "county",
                5: "location_name",
                6: "address",
                7: "municipality",
                8: "plss_description",
                9: "latitude",
                10: "longitude",
                11: "acres",
                12: "facility_id",
                13: "pecfa_number",
                14: "epa_id",
                15: "start_date",
                16: "end_date",
            }
            
            for idx, key in field_positions.items():
                if idx < len(values):
                    val = values[idx].strip()
                    if val and val not in ['', ' ', 'UNKNOWN'] or key in ['acres']:
                        # Don't overwrite location_name if we got it from header
                        if key == "location_name" and "location_name" in site_info:
                            continue
                        site_info[key] = val
            
            # Fix: if acres is UNKNOWN, keep it
            if site_info.get("acres") == "":
                site_info["acres"] = "UNKNOWN"
            
            # Characteristics are at positions 18-26 (indices in the values list starting after site info)
            # The characteristic labels are:
            # 18: Above Ground Petrol Tank
            # 19: Dry Cleaner
            # 20: EPA NPL Site
            # 21: PECFA Funds Eligible
            # 22: PFAS
            # 23: ROW Impact
            # 24: Sediments
            # 25: WI DOT Site
            # 26: Underground Petrol Tank
            
            risk_flags = {
                "status_label": site_info.get("status", "UNKNOWN").upper(),
                "pfas": False,
                "petroleum": False,
                "heavy_metals": False,
                "chlorinated_solvents": False,
                "offsite_impact": False,
                "underground_tank": False,
                "above_ground_tank": False,
            }
            
            # Characteristics values start at index 17 (after site info fields)
            char_offset = 17
            char_map = {
                0: "above_ground_tank",
                1: "dry_cleaner",
                2: "epa_npl",
                3: "pecfa_eligible",
                4: "pfas",
                5: "row_impact",
                6: "sediments",
                7: "wi_dot",
                8: "underground_tank",
            }
            
            for char_idx, char_name in char_map.items():
                val_idx = char_offset + char_idx
                if val_idx < len(values):
                    val = values[val_idx].strip().lower()
                    if val == "yes":
                        if char_name == "pfas":
                            risk_flags["pfas"] = True
                        elif char_name == "underground_tank":
                            risk_flags["petroleum"] = True
                            risk_flags["underground_tank"] = True
                        elif char_name == "above_ground_tank":
                            risk_flags["petroleum"] = True
                            risk_flags["above_ground_tank"] = True
                        elif char_name == "row_impact":
                            risk_flags["offsite_impact"] = True
            
            # Also check if activity type is LUST
            if site_info.get("activity_type", "").upper() == "LUST":
                risk_flags["petroleum"] = True
            
            # Check page text for additional contaminants
            page_lower = page_text.lower()
            if "petroleum" in page_lower:
                risk_flags["petroleum"] = True
            if any(metal in page_lower for metal in ['arsenic', 'lead', 'chromium', 'mercury', 'cadmium']):
                risk_flags["heavy_metals"] = True
            if any(solvent in page_lower for solvent in ['tce', 'pce', 'trichloroethylene', 'tetrachloroethylene', 'chlorinated']):
                risk_flags["chlorinated_solvents"] = True
            
            # Extract documents
            documents = []
            links = page.locator("a[href*='download-document'], a[href*='docSeqNo']").all()
            
            seen_urls = set()
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if href and href not in seen_urls:
                        seen_urls.add(href)
                        if not href.startswith("http"):
                            href = f"https://apps.dnr.wi.gov{href}"
                        
                        seq_match = re.search(r'docSeqNo=(\d+)', href)
                        seq_no = seq_match.group(1) if seq_match else str(len(documents))
                        
                        documents.append({
                            "id": len(documents),
                            "download_url": href,
                            "category": "Site File",
                            "date": "",
                            "action_code": "",
                            "name": f"Site File Documentation (ID: {seq_no})",
                            "comment": "DNR site documentation",
                        })
                except:
                    continue
            
            browser.close()
            
            result["site_info"] = site_info
            result["risk_flags"] = risk_flags
            result["documents"] = documents
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing DSN argument"}))
        sys.exit(1)
    
    dsn = sys.argv[1]
    result = scrape_brrts_site(dsn)
    print(json.dumps(result))
