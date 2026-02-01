"""
Document Scraper Module
-----------------------
Scrapes site info and documents from Wisconsin DNR BRRTS pages.
Uses Playwright via subprocess locally, falls back to requests on serverless.
"""

import subprocess
import json
import sys
import os
import requests
from bs4 import BeautifulSoup
import re


def extract_site_and_documents(dsn: str) -> dict:
    """
    Scrape all site information and documents from the BRRTS activity detail page.
    Uses Playwright in a subprocess for full scraping, falls back to requests.
    
    Args:
        dsn: The 6-digit DSN (Data Serial Number)
        
    Returns:
        Dictionary with 'site_info', 'risk_flags', 'documents', and 'summary'
    """
    
    # Try Playwright first (works locally and on Railway/Render)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scraper_path = os.path.join(script_dir, "playwright_scraper.py")
    
    print(f"[document_scraper] Looking for Playwright scraper at: {scraper_path}")
    print(f"[document_scraper] Scraper exists: {os.path.exists(scraper_path)}")
    
    if os.path.exists(scraper_path):
        try:
            print(f"[document_scraper] Running Playwright scraper for DSN: {dsn}")
            result = subprocess.run(
                [sys.executable, scraper_path, dsn],
                capture_output=True,
                text=True,
                timeout=120  # Increased timeout for cloud
            )
            
            print(f"[document_scraper] Playwright return code: {result.returncode}")
            if result.stderr:
                print(f"[document_scraper] Playwright stderr: {result.stderr[:500]}")
            
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if not data.get("error"):
                    site_info = data.get("site_info", {"dsn": dsn})
                    risk_flags = data.get("risk_flags", {"status_label": "UNKNOWN"})
                    documents = data.get("documents", [])
                    summary = generate_summary(site_info, risk_flags, len(documents))
                    
                    print(f"[document_scraper] Playwright success! Got {len(documents)} documents")
                    
                    return {
                        "site_info": site_info,
                        "risk_flags": risk_flags,
                        "documents": documents,
                        "summary": summary,
                        "error": None
                    }
                else:
                    print(f"[document_scraper] Playwright returned error: {data.get('error')}")
            else:
                print(f"[document_scraper] Playwright failed. stdout: {result.stdout[:200] if result.stdout else 'empty'}")
        except subprocess.TimeoutExpired:
            print(f"[document_scraper] Playwright timed out after 120s")
        except json.JSONDecodeError as e:
            print(f"[document_scraper] Failed to parse Playwright output: {e}")
        except Exception as e:
            print(f"[document_scraper] Playwright scraper exception: {type(e).__name__}: {e}")
    
    print("[document_scraper] Falling back to basic requests scraping")
    
    # Final fallback to requests-based scraping (limited data)
    return extract_with_requests(dsn)


def extract_with_requests(dsn: str) -> dict:
    """Fallback scraper using requests and BeautifulSoup."""
    url = f"https://apps.dnr.wi.gov/rrbotw/botw-activity-detail?dsn={dsn}"
    
    site_info = {"dsn": dsn}
    risk_flags = {"status_label": "UNKNOWN"}
    documents = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        
        # Try to extract activity number from header
        header_match = re.search(r'(\d{2}-\d{2}-\d+)\s+([A-Z][A-Z0-9\s\'\-\.]+?)(?:\s*Activity Type|\s*$)', page_text)
        if header_match:
            site_info["activity_number"] = header_match.group(1)
            site_info["location_name"] = header_match.group(2).strip()
        
        # Find document links
        doc_links = soup.find_all('a', href=re.compile(r'download-document|docSeqNo'))
        seen_urls = set()
        
        for link in doc_links:
            href = link.get('href', '')
            if href and href not in seen_urls:
                seen_urls.add(href)
                if not href.startswith('http'):
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
        
        # Check for petroleum/LUST
        if 'lust' in page_text.lower() or 'petroleum' in page_text.lower():
            risk_flags["petroleum"] = True
        
        summary = generate_summary(site_info, risk_flags, len(documents))
        
        return {
            "site_info": site_info,
            "risk_flags": risk_flags,
            "documents": documents,
            "summary": summary,
            "error": None,
            "note": "Limited data - JavaScript content not available in serverless mode"
        }
        
    except Exception as e:
        return {
            "site_info": {"dsn": dsn},
            "risk_flags": {"status_label": "UNKNOWN"},
            "documents": [],
            "summary": f"Error: {str(e)}",
            "error": str(e)
        }


def extract_documents(dsn: str) -> dict:
    """Legacy function - calls the comprehensive extractor."""
    result = extract_site_and_documents(dsn)
    return {
        "documents": result.get("documents", []),
        "error": result.get("error")
    }


def generate_summary(site_info: dict, risk_flags: dict, doc_count: int) -> str:
    """Generate a summary based on extracted data."""
    location = site_info.get("location_name", "Unknown Location")
    activity_num = site_info.get("activity_number", site_info.get("dsn", "Unknown"))
    status = site_info.get("status", risk_flags.get("status_label", "Unknown"))
    activity_type = site_info.get("activity_type", "Unknown")
    address = site_info.get("address", "")
    municipality = site_info.get("municipality", "")
    county = site_info.get("county", "")
    
    location_parts = [location]
    if address:
        location_parts.append(f"at {address}")
    if municipality:
        location_parts.append(municipality)
    if county:
        location_parts.append(f"{county} County")
    location_str = ", ".join(filter(None, location_parts))
    
    risks = []
    if risk_flags.get("petroleum"):
        risks.append("Petroleum contamination indicated (LUST site)")
    if risk_flags.get("pfas"):
        risks.append("PFAS contamination present")
    if risk_flags.get("heavy_metals"):
        risks.append("Heavy metals detected")
    if risk_flags.get("chlorinated_solvents"):
        risks.append("Chlorinated solvents present")
    if risk_flags.get("offsite_impact"):
        risks.append("Off-site or ROW impact noted")
    
    risk_text = '\n'.join(f'- {r}' for r in risks) if risks else '- No major risk indicators identified from site data'
    
    summary = f"""Site: {location_str}
Activity: {activity_num} | Type: {activity_type} | Status: {status}

Start Date: {site_info.get('start_date', 'Unknown')}
End Date: {site_info.get('end_date', 'N/A')}

Risk Indicators:
{risk_text}

Documents Available: {doc_count}

Recommendations:
- Select documents and click "Extract Text" to analyze content
- For legal decisions, always conduct professional Phase I/II ESA review"""
    
    return summary


def get_document_summary(documents: list) -> str:
    """Create a text summary of selected documents for AI context."""
    if not documents:
        return "No documents selected."
    
    lines = [f"Selected Documents ({len(documents)} total):\n"]
    
    for i, doc in enumerate(documents, 1):
        lines.append(f"{i}. {doc.get('name', 'Unnamed Document')}")
        if doc.get('category'):
            lines.append(f"   Category: {doc.get('category')}")
        if doc.get('date'):
            lines.append(f"   Date: {doc.get('date')}")
        if doc.get('action_code'):
            lines.append(f"   Action Code: {doc.get('action_code')}")
        if doc.get('comment'):
            lines.append(f"   Comment: {doc.get('comment')}")
        lines.append("")
    
    return "\n".join(lines)
