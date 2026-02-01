from flask import Flask, Response
import os
import re

# Get the base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

# Read template files
def read_template(name):
    template_path = os.path.join(BASE_DIR, 'templates', name)
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"<h1>Error loading template: {e}</h1><p>Path: {template_path}</p>"

def read_static(name):
    static_path = os.path.join(BASE_DIR, 'static', name)
    try:
        with open(static_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"// Error: {e}"

def scrape_dnr_site(dsn):
    """Scrape DNR BRRTS site using Browserless.io API for JS rendering"""
    import requests
    from bs4 import BeautifulSoup
    
    site_info = {
        "dsn": dsn,
        "activity_number": f"XX-XX-{dsn}",
        "status": "Not available",
        "activity_type": "Not available",
        "location_name": "Not available",
        "address": "Not available",
        "municipality": "Not available",
        "county": "Not available",
        "region": "Not available",
        "start_date": "Not available",
        "end_date": "Not available",
    }
    
    risk_flags = {}
    documents = []
    
    url = f"https://apps.dnr.wi.gov/rrbotw/botw-activity-detail?dsn={dsn}"
    
    # Try Browserless.io first (renders JavaScript)
    browserless_key = os.environ.get("BROWSERLESS_API_KEY", "")
    
    if browserless_key:
        try:
            # Use /content endpoint to get fully rendered HTML
            api_url = f"https://chrome.browserless.io/content?token={browserless_key}"
            payload = {
                "url": url,
                "waitFor": 8000,
                "gotoOptions": {
                    "waitUntil": "networkidle0",
                    "timeout": 45000
                }
            }
            
            resp = requests.post(api_url, json=payload, timeout=90, headers={"Content-Type": "application/json"})
            
            if resp.status_code == 200:
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract from rendered page - get all input values
                inputs = soup.find_all('input', class_='form-control')
                values = []
                for inp in inputs:
                    val = inp.get('value', '').strip()
                    values.append(val)
                
                # Map values by position (same as Playwright scraper)
                field_map = {
                    0: "activity_type",
                    1: "status",
                    2: "jurisdiction",
                    3: "region",
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
                
                for idx, key in field_map.items():
                    if idx < len(values) and values[idx]:
                        site_info[key] = values[idx]
                
                # Get activity number from header
                page_text = soup.get_text()
                header_match = re.search(r'(\d{2}-\d{2}-\d+)\s+([A-Z][A-Z0-9\s\'\-\.]+)', page_text)
                if header_match:
                    site_info["activity_number"] = header_match.group(1)
                    # Use header name if location_name looks like a placeholder
                    if site_info["location_name"] in ["Not available", "Location Name", ""]:
                        site_info["location_name"] = header_match.group(2).strip()
                
                # Risk flags
                status = site_info.get("status", "").upper()
                risk_flags["status_label"] = status if status else "UNKNOWN"
                
                if site_info.get("activity_type", "").upper() == "LUST":
                    risk_flags["petroleum"] = True
                if "pfas" in page_text.lower():
                    risk_flags["pfas"] = True
                if any(m in page_text.lower() for m in ['arsenic', 'lead', 'mercury']):
                    risk_flags["heavy_metals"] = True
                
                # Documents
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if 'download-document' in href or 'docSeqNo' in href:
                        if not href.startswith('http'):
                            href = f"https://apps.dnr.wi.gov{href}"
                        seq_match = re.search(r'docSeqNo=(\d+)', href)
                        if seq_match:
                            seq_no = seq_match.group(1)
                            documents.append({
                                "id": len(documents),
                                "download_url": href,
                                "category": "Site File",
                                "name": f"Site File (ID: {seq_no})",
                            })
                
                summary = f"{site_info.get('location_name', 'Site')} - {site_info.get('status', 'Unknown')}"
                return site_info, risk_flags, documents, summary
                
        except Exception as e:
            print(f"Browserless error: {e}")
    
    # Fallback to basic requests (limited data)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=30)
        
        if resp.status_code != 200:
            return site_info, risk_flags, documents, f"Failed to fetch page: {resp.status_code}"
        
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try to extract from the page title/header
        title = soup.find('title')
        if title:
            title_text = title.get_text()
            # Title often contains location name
            if ' - ' in title_text:
                site_info["location_name"] = title_text.split(' - ')[0].strip()
        
        # Look for the header with location name
        header = soup.find('h1') or soup.find('h2')
        if header:
            header_text = header.get_text().strip()
            if header_text and len(header_text) > 3:
                site_info["location_name"] = header_text
        
        # Extract from Angular app data if present
        scripts = soup.find_all('script')
        for script in scripts:
            script_text = script.string or ""
            # Look for activity data in scripts
            if 'activityType' in script_text or 'ActivityType' in script_text:
                # Try to extract JSON data
                pass
        
        # Look for specific elements with data
        # Try finding input fields (readonly form fields often have data)
        inputs = soup.find_all('input')
        for inp in inputs:
            value = inp.get('value', '').strip()
            name = (inp.get('name') or inp.get('id') or '').lower()
            placeholder = (inp.get('placeholder') or '').lower()
            
            if not value:
                continue
                
            if 'status' in name or 'status' in placeholder:
                site_info["status"] = value
            elif 'type' in name and 'activity' in name:
                site_info["activity_type"] = value
            elif 'location' in name or 'name' in name:
                if value and site_info["location_name"] == "Not available":
                    site_info["location_name"] = value
            elif 'address' in name or 'street' in name:
                site_info["address"] = value
            elif 'municipal' in name or 'city' in name:
                site_info["municipality"] = value
            elif 'county' in name:
                site_info["county"] = value
            elif 'region' in name:
                site_info["region"] = value
        
        # Try to find data in table cells or definition lists
        for td in soup.find_all(['td', 'dd', 'span', 'div']):
            text = td.get_text().strip()
            prev = td.find_previous_sibling()
            prev_text = prev.get_text().strip().lower() if prev else ""
            
            # Also check parent label
            parent = td.parent
            if parent:
                label = parent.find(['th', 'dt', 'label'])
                if label:
                    prev_text = label.get_text().strip().lower()
            
            if not text or len(text) > 200:
                continue
                
            if 'status' in prev_text and site_info["status"] == "Not available":
                site_info["status"] = text
            elif 'activity type' in prev_text and site_info["activity_type"] == "Not available":
                site_info["activity_type"] = text
            elif 'county' in prev_text and site_info["county"] == "Not available":
                site_info["county"] = text
            elif 'municipality' in prev_text and site_info["municipality"] == "Not available":
                site_info["municipality"] = text
            elif 'region' in prev_text and site_info["region"] == "Not available":
                site_info["region"] = text
        
        # Extract activity number from page content
        activity_match = re.search(r'(\d{2}-\d{2}-\d{6})', html)
        if activity_match:
            site_info["activity_number"] = activity_match.group(1)
        
        # Look for status in page text
        status_patterns = [
            (r'Status[:\s]+([A-Z]+(?:\s+[A-Z]+)?)', 'status'),
            (r'Activity Type[:\s]+([A-Za-z\s\-]+?)(?=\s*<|\s*$)', 'activity_type'),
        ]
        for pattern, field in status_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match and site_info[field] == "Not available":
                site_info[field] = match.group(1).strip()
        
        # Detect risk flags from page content
        page_text = html.lower()
        if 'lust' in page_text or 'leaking underground' in page_text:
            risk_flags['lust'] = True
        if 'petroleum' in page_text or 'gasoline' in page_text or 'diesel' in page_text:
            risk_flags['petroleum'] = True
        if 'pfas' in page_text or 'pfoa' in page_text or 'pfos' in page_text:
            risk_flags['pfas'] = True
        if 'arsenic' in page_text or 'lead' in page_text or 'mercury' in page_text:
            risk_flags['heavy_metals'] = True
        if 'groundwater' in page_text and ('contamina' in page_text or 'impact' in page_text):
            risk_flags['groundwater'] = True
        if 'off-site' in page_text or 'offsite' in page_text:
            risk_flags['offsite_impact'] = True
        
        # Extract document links
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'download-document' in href or 'docSeqNo' in href:
                doc_name = link.get_text().strip() or "Document"
                # Extract docSeqNo
                seq_match = re.search(r'docSeqNo=(\d+)', href)
                if seq_match:
                    doc_seq = seq_match.group(1)
                    full_url = href if href.startswith('http') else f"https://apps.dnr.wi.gov{href}"
                    documents.append({
                        "id": len(documents),
                        "name": doc_name,
                        "download_url": full_url,
                        "category": "Site File",
                        "doc_seq_no": doc_seq
                    })
        
        # Try the BRRTS API directly
        try:
            api_url = f"https://apps.dnr.wi.gov/rrbotw/api/activity/{dsn}"
            api_resp = requests.get(api_url, headers=headers, timeout=10)
            if api_resp.status_code == 200:
                api_data = api_resp.json()
                if isinstance(api_data, dict):
                    site_info["status"] = api_data.get("status") or api_data.get("Status") or site_info["status"]
                    site_info["activity_type"] = api_data.get("activityType") or api_data.get("ActivityType") or site_info["activity_type"]
                    site_info["location_name"] = api_data.get("locationName") or api_data.get("LocationName") or site_info["location_name"]
                    site_info["address"] = api_data.get("address") or api_data.get("Address") or site_info["address"]
                    site_info["municipality"] = api_data.get("municipality") or api_data.get("Municipality") or site_info["municipality"]
                    site_info["county"] = api_data.get("county") or api_data.get("County") or site_info["county"]
                    site_info["region"] = api_data.get("region") or api_data.get("Region") or site_info["region"]
                    site_info["start_date"] = api_data.get("startDate") or api_data.get("StartDate") or site_info["start_date"]
                    site_info["end_date"] = api_data.get("endDate") or api_data.get("EndDate") or site_info["end_date"]
                    site_info["activity_number"] = api_data.get("activityNumber") or api_data.get("ActivityNumber") or site_info["activity_number"]
        except:
            pass
        
        # Try document API
        try:
            docs_url = f"https://apps.dnr.wi.gov/rrbotw/api/activity/{dsn}/documents"
            docs_resp = requests.get(docs_url, headers=headers, timeout=10)
            if docs_resp.status_code == 200:
                docs_data = docs_resp.json()
                if isinstance(docs_data, list):
                    for doc in docs_data:
                        doc_seq = doc.get("docSeqNo") or doc.get("documentSeqNo") or doc.get("id")
                        if doc_seq:
                            documents.append({
                                "id": len(documents),
                                "name": doc.get("description") or doc.get("name") or doc.get("fileName") or f"Document {doc_seq}",
                                "download_url": f"https://apps.dnr.wi.gov/rrbotw/download-document?docSeqNo={doc_seq}&sender=activity",
                                "category": doc.get("category") or doc.get("documentType") or "Site File",
                                "doc_seq_no": str(doc_seq),
                                "comment": doc.get("comment") or ""
                            })
        except:
            pass
        
        summary = f"Site {dsn} analyzed."
        if site_info["location_name"] != "Not available":
            summary = f"{site_info['location_name']} - {site_info.get('status', 'Unknown status')}"
        
        return site_info, risk_flags, documents, summary
        
    except Exception as e:
        return site_info, risk_flags, documents, f"Error scraping: {str(e)}"

@app.route("/")
def landing():
    return Response(read_template('landing.html'), mimetype='text/html')

@app.route("/app")
def index():
    return Response(read_template('index.html'), mimetype='text/html')

@app.route("/static/main.js")
def main_js():
    return Response(read_static('main.js'), mimetype='application/javascript')

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    from flask import request, jsonify
    data = request.get_json() or {}
    brrts_id = (data.get("brrts") or "").strip()
    
    if not brrts_id:
        return jsonify({"error": "Missing BRRTS activity ID."}), 400
    
    digits_only = ''.join(c for c in brrts_id if c.isdigit())
    dsn = digits_only[-6:] if len(digits_only) >= 6 else digits_only
    
    # Actually scrape the DNR site
    site_info, risk_flags, documents, summary = scrape_dnr_site(dsn)
    
    return jsonify({
        "site_info": site_info,
        "risk_flags": risk_flags,
        "summary": summary,
        "documents_available": len(documents),
        "documents": documents
    })

@app.route("/api/documents", methods=["POST"])
def api_documents():
    from flask import request, jsonify
    data = request.get_json() or {}
    dsn = (data.get("dsn") or "").strip()
    
    if not dsn:
        return jsonify({"documents": [], "count": 0})
    
    # Scrape documents
    _, _, documents, _ = scrape_dnr_site(dsn)
    
    return jsonify({
        "documents": documents,
        "count": len(documents),
        "extraction_available": True
    })

@app.route("/api/documents/add", methods=["POST"])
def api_add_document():
    from flask import request, jsonify
    data = request.get_json() or {}
    doc_seq_no = (data.get("docSeqNo") or "").strip()
    
    if not doc_seq_no:
        return jsonify({"error": "Missing docSeqNo."}), 400
    
    return jsonify({
        "document": {
            "id": 0,
            "download_url": f"https://apps.dnr.wi.gov/rrbotw/download-document?docSeqNo={doc_seq_no}&sender=activity",
            "category": "Site File",
            "name": f"Site File (ID: {doc_seq_no})",
            "comment": "Manually added",
            "doc_seq_no": doc_seq_no
        },
        "success": True
    })

@app.route("/api/documents/extract", methods=["POST"])
def api_extract():
    from flask import request, jsonify
    import requests as req
    
    data = request.get_json() or {}
    documents = data.get("documents") or []
    
    if not documents:
        return jsonify({"error": "No documents provided."}), 400
    
    # Try to extract text from PDFs
    extracted = []
    combined_text = ""
    
    for doc in documents[:5]:  # Limit to 5 docs
        url = doc.get("download_url", "")
        if not url:
            continue
            
        try:
            resp = req.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200 and len(resp.content) > 100:
                # Try pypdf
                try:
                    import pypdf
                    import io
                    reader = pypdf.PdfReader(io.BytesIO(resp.content))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                    doc["extracted_text"] = text[:20000]
                    doc["extraction_status"] = "success"
                    combined_text += f"\n\n=== {doc.get('name', 'Document')} ===\n{text[:20000]}"
                except Exception as pdf_err:
                    doc["extraction_status"] = f"pdf_error: {str(pdf_err)}"
            else:
                doc["extraction_status"] = f"download_failed: {resp.status_code}"
        except Exception as e:
            doc["extraction_status"] = f"error: {str(e)}"
        
        extracted.append(doc)
    
    successful = sum(1 for d in extracted if d.get('extraction_status') == 'success')
    
    return jsonify({
        "documents": extracted,
        "combined_text": combined_text[:50000],
        "risk_analysis": {"risk_flags": {}},
        "extraction_summary": {
            "total": len(documents),
            "successful": successful,
            "failed": len(documents) - successful,
            "total_text_length": len(combined_text)
        }
    })

@app.route("/api/documents/summarize", methods=["POST"])
def api_summarize():
    from flask import request, jsonify
    from openai import OpenAI
    
    data = request.get_json() or {}
    combined_text = data.get("combined_text", "")
    site_data = data.get("site_data", {})
    
    if not combined_text:
        return jsonify({"error": "No text to summarize."}), 400
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENROUTER_API_KEY not set in Vercel environment variables."}), 400
    
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        
        site_context = ""
        if site_data:
            site_context = f"""
Site Information:
- Location: {site_data.get('location_name', 'Unknown')}
- Address: {site_data.get('address', 'Unknown')}
- County: {site_data.get('county', 'Unknown')}
- Status: {site_data.get('status', 'Unknown')}
- Activity Type: {site_data.get('activity_type', 'Unknown')}
"""
        
        prompt = f"""You are an environmental due diligence analyst reviewing Wisconsin DNR BRRTS documents.

{site_context}

Please analyze the following document text and provide a comprehensive summary including:
1. **Site Overview**: Brief description of the site and contamination history
2. **Contamination Summary**: Types of contaminants found, concentrations, and affected media
3. **Remediation Status**: Actions taken or planned to address contamination
4. **Regulatory Status**: Current status with DNR, any violations or ongoing requirements
5. **Key Risk Factors**: Main environmental concerns for due diligence purposes
6. **Recommendations**: Suggested next steps for a potential property transaction

Document Text:
{combined_text[:35000]}"""
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": "You are an expert environmental due diligence analyst specializing in Wisconsin contaminated sites."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000
        )
        
        return jsonify({"summary": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
def api_chat():
    from flask import request, jsonify
    from openai import OpenAI
    
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    selected_docs = data.get("selected_documents") or []
    site_data = data.get("site_data", {})
    
    if not question:
        return jsonify({"error": "No question."}), 400
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"answer": "AI requires OPENROUTER_API_KEY to be set in Vercel environment variables.", "history": []})
    
    # Get any extracted text
    doc_text = "\n\n".join(d.get("extracted_text", "")[:10000] for d in selected_docs if d.get("extracted_text"))
    
    site_context = ""
    if site_data:
        site_context = f"Site: {site_data.get('location_name', 'Unknown')} in {site_data.get('county', 'Unknown')} County. Status: {site_data.get('status', 'Unknown')}."
    
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": f"You are an environmental due diligence analyst. {site_context}\n\nDocument context:\n{doc_text[:20000]}"},
                {"role": "user", "content": question}
            ],
            max_tokens=2000
        )
        
        return jsonify({
            "answer": response.choices[0].message.content,
            "session_id": "vercel",
            "history": []
        })
    except Exception as e:
        return jsonify({"answer": f"Error: {e}", "history": []})
