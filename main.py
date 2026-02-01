"""
AI Due Diligence - Flask Application
------------------------------------
A web application for analyzing Wisconsin DNR BRRTS environmental data
with document scraping, PDF text extraction, and AI-powered Q&A.
"""

import os
import json
import uuid
import base64
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from brrts_client import fetch_site_data
from document_scraper import extract_documents, extract_site_and_documents, get_document_summary
from filedownload import get_or_create_session, cleanup_session
from pdf_extractor import (
    extract_document_text, 
    extract_all_documents, 
    analyze_extracted_text_for_risks,
    get_extraction_capabilities
)
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())


def get_openrouter_client():
    """Create OpenAI client configured for OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


@app.after_request
def add_header(response):
    """Add headers to prevent caching for development."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/")
def landing():
    """Render the landing page."""
    return render_template("landing.html")


@app.route("/app")
def index():
    """Render the main application page."""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Analyze a BRRTS site by scraping the actual DNR page."""
    data = request.get_json() or {}
    brrts_id = (data.get("brrts") or "").strip()
    
    if not brrts_id:
        return jsonify({"error": "Missing BRRTS activity ID."}), 400
    
    # Extract DSN (6-digit number)
    digits_only = ''.join(c for c in brrts_id if c.isdigit())
    dsn = digits_only[-6:] if len(digits_only) >= 6 else digits_only
    
    try:
        # Use Playwright to scrape the actual DNR page
        result = extract_site_and_documents(dsn)
        
        if result.get("error"):
            return jsonify({
                "site_info": {"dsn": dsn},
                "risk_flags": {"status_label": "UNKNOWN"},
                "summary": f"Error loading site: {result['error']}",
                "error": result["error"]
            }), 500
        
        return jsonify({
            "site_info": result.get("site_info", {"dsn": dsn}),
            "risk_flags": result.get("risk_flags", {"status_label": "UNKNOWN"}),
            "summary": result.get("summary", "Site data loaded. Fetch documents and extract text for detailed analysis."),
            "documents_available": len(result.get("documents", []))
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to analyze site: {str(e)}"}), 500


@app.route("/api/documents", methods=["POST"])
def api_documents():
    """
    Fetch documents for a BRRTS site.
    Returns list of documents with metadata.
    """
    data = request.get_json() or {}
    dsn = (data.get("dsn") or "").strip()
    
    if not dsn:
        return jsonify({"error": "Missing DSN."}), 400
    
    digits_only = ''.join(c for c in dsn if c.isdigit())
    if len(digits_only) >= 6:
        dsn = digits_only[-6:]
    
    # Use comprehensive scraper
    result = extract_site_and_documents(dsn)
    
    if result.get("error"):
        return jsonify({
            "documents": [],
            "error": result["error"]
        }), 500
    
    documents = result.get("documents", [])
    
    return jsonify({
        "documents": documents,
        "count": len(documents),
        "extraction_available": get_extraction_capabilities()['can_extract']
    })


@app.route("/api/documents/add", methods=["POST"])
def api_add_document():
    """
    Manually add a document by docSeqNo or URL.
    """
    data = request.get_json() or {}
    doc_seq_no = (data.get("docSeqNo") or "").strip()
    doc_url = (data.get("url") or "").strip()
    dsn = (data.get("dsn") or "").strip()
    
    if not doc_seq_no and not doc_url:
        return jsonify({"error": "Missing docSeqNo or URL."}), 400
    
    if doc_seq_no:
        download_url = f"https://apps.dnr.wi.gov/rrbotw/download-document?docSeqNo={doc_seq_no}&sender=activity"
    else:
        download_url = doc_url
    
    document = {
        "id": 0,
        "download_url": download_url,
        "category": "Site File",
        "date": "",
        "action_code": "",
        "name": f"Site File Documentation (ID: {doc_seq_no or 'Manual'})",
        "comment": "Manually added document",
    }
    
    return jsonify({
        "document": document,
        "success": True
    })


@app.route("/api/documents/summarize", methods=["POST"])
def api_summarize_documents():
    """
    Generate an AI summary of extracted document text.
    """
    data = request.get_json() or {}
    combined_text = data.get("combined_text", "")
    site_data = data.get("site_data", {})
    documents = data.get("documents", [])
    
    if not combined_text:
        return jsonify({"error": "No document text to summarize."}), 400
    
    client = get_openrouter_client()
    if not client:
        return jsonify({"error": "OPENROUTER_API_KEY not configured. Add it to your .env file."}), 400
    
    try:
        site_info = site_data.get("site_info", {})
        
        # Build context
        site_context = f"""
Site: {site_info.get('location_name', 'Unknown')}
Activity Number: {site_info.get('activity_number', 'Unknown')}
Status: {site_info.get('status', 'Unknown')}
Activity Type: {site_info.get('activity_type', 'Unknown')}
Address: {site_info.get('address', 'Unknown')}, {site_info.get('municipality', '')}, {site_info.get('county', '')} County
"""
        
        # Truncate text to fit in context
        max_text = 35000
        truncated_text = combined_text[:max_text]
        if len(combined_text) > max_text:
            truncated_text += "\n\n[Document text truncated due to length...]"
        
        prompt = f"""Analyze the following environmental site documents and provide a comprehensive due diligence summary.

{site_context}

DOCUMENT TEXT:
{truncated_text}

Provide a structured summary including:

1. **SITE OVERVIEW**: Brief description of the property and contamination history

2. **CONTAMINATION SUMMARY**:
   - Types of contamination found (petroleum, PFAS, heavy metals, solvents, etc.)
   - Specific contaminants and concentrations mentioned
   - Media affected (soil, groundwater, soil vapor)

3. **REMEDIATION STATUS**:
   - What cleanup actions have been taken
   - Current status of remediation
   - Any ongoing monitoring requirements

4. **REGULATORY STATUS**:
   - Case status (Open/Closed)
   - Any closure letters or No Further Action determinations
   - Continuing obligations or deed restrictions

5. **KEY RISK FACTORS**:
   - Significant environmental concerns
   - Off-site migration or impact
   - Vapor intrusion potential
   - Groundwater impact

6. **RECOMMENDATIONS**:
   - Additional investigation needs
   - Due diligence considerations for property acquisition

Be specific and cite information from the documents where possible."""

        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": "You are an environmental due diligence analyst specializing in contaminated property assessment. Provide clear, professional analysis suitable for commercial real estate transactions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000
        )
        
        summary = response.choices[0].message.content or "No summary generated."
        
        return jsonify({
            "summary": summary,
            "documents_analyzed": len(documents),
            "text_length": len(combined_text)
        })
        
    except Exception as e:
        return jsonify({"error": f"AI summarization failed: {str(e)}"}), 500


@app.route("/api/documents/extract", methods=["POST"])
def api_extract_documents():
    """
    Extract text content from selected documents.
    Downloads PDFs and extracts all text for analysis.
    """
    data = request.get_json() or {}
    documents = data.get("documents") or []
    
    if not documents:
        return jsonify({"error": "No documents provided."}), 400
    
    # Check extraction capabilities
    caps = get_extraction_capabilities()
    if not caps['can_extract']:
        return jsonify({
            "error": "PDF extraction libraries not available. Install pypdf or pdfminer.six.",
            "capabilities": caps
        }), 500
    
    try:
        # Extract text from all documents
        extracted_docs, combined_text = extract_all_documents(documents, max_documents=20)
        
        # Analyze the extracted text for risk indicators
        risk_analysis = analyze_extracted_text_for_risks(combined_text)
        
        # Count successful extractions
        successful = sum(1 for d in extracted_docs if d.get('extraction_status') == 'success')
        
        return jsonify({
            "documents": extracted_docs,
            "combined_text": combined_text[:50000] if combined_text else "",  # Limit size
            "risk_analysis": risk_analysis,
            "extraction_summary": {
                "total": len(documents),
                "successful": successful,
                "failed": len(documents) - successful,
                "total_text_length": len(combined_text)
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {str(e)}"}), 500


@app.route("/api/analyze-with-documents", methods=["POST"])
def api_analyze_with_documents():
    """
    Comprehensive analysis that extracts text from all documents
    and uses AI to analyze the full content.
    """
    data = request.get_json() or {}
    brrts_id = (data.get("brrts") or "").strip()
    
    if not brrts_id:
        return jsonify({"error": "Missing BRRTS activity ID."}), 400
    
    client = get_openrouter_client()
    if not client:
        return jsonify({"error": "OPENROUTER_API_KEY not set in environment."}), 400
    
    # Extract DSN from BRRTS ID
    digits_only = ''.join(c for c in brrts_id if c.isdigit())
    dsn = digits_only[-6:] if len(digits_only) >= 6 else digits_only
    
    try:
        # Step 1: Fetch document list
        doc_result = extract_documents(dsn)
        documents = doc_result.get("documents", [])
        
        # Step 2: Extract text from all documents
        extracted_docs = []
        combined_text = ""
        risk_from_docs = {}
        
        if documents and get_extraction_capabilities()['can_extract']:
            extracted_docs, combined_text = extract_all_documents(documents, max_documents=15)
            risk_from_docs = analyze_extracted_text_for_risks(combined_text)
        
        search_url = f"https://apps.dnr.wi.gov/rrbotw/botw-activity-detail?DSN={dsn}"
        
        # Build comprehensive prompt with extracted document text
        doc_text_section = ""
        if combined_text:
            # Truncate to reasonable size for API
            truncated_text = combined_text[:30000]
            doc_text_section = f"""

EXTRACTED DOCUMENT TEXT (from {len(extracted_docs)} documents):
{truncated_text}
{"[Text truncated due to length...]" if len(combined_text) > 30000 else ""}
"""
        
        prompt = f"""Analyze this Wisconsin DNR BRRTS site: {search_url}

{doc_text_section}

Based on the extracted document text above, extract:

1. Site Information:
- DSN, Activity Number, Status, Activity Type
- Location Name, Address, Municipality, County, DNR Region
- Start Date, End Date

2. Environmental Risk Analysis from the documents:
- PFAS contamination (true/false with evidence from documents)
- Petroleum contamination (true/false with evidence)
- Heavy metals contamination (true/false with evidence)
- Chlorinated solvents (true/false with evidence)
- Off-site impact (true/false with evidence)
- Groundwater impact details
- Soil contamination details

3. Key findings from the documents including:
- Contamination concentrations found
- Remediation status
- Any closure letters or no further action determinations
- Continuing obligations or restrictions

Return as JSON:
{{
  "site_info": {{
    "dsn": "...",
    "activity_number": "...",
    "status": "...",
    "activity_type": "...",
    "location_name": "...",
    "address": "...",
    "municipality": "...",
    "county": "...",
    "dnr_region": "...",
    "start_date": "...",
    "end_date": "..."
  }},
  "risk_flags": {{
    "status_label": "OPEN" or "CLOSED",
    "pfas": true/false,
    "petroleum": true/false,
    "heavy_metals": true/false,
    "chlorinated_solvents": true/false,
    "offsite_impact": true/false
  }},
  "document_findings": {{
    "contamination_details": "...",
    "remediation_status": "...",
    "closure_status": "...",
    "key_concentrations": ["..."],
    "restrictions": "..."
  }},
  "summary": "Comprehensive summary based on all documents..."
}}"""

        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": "You are an environmental due diligence analyst. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2048
        )
        
        response_text = response.choices[0].message.content or ""
        
        # Parse JSON response
        try:
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
            else:
                json_str = response_text.strip()
            
            site_data = json.loads(json_str)
        except json.JSONDecodeError:
            site_data = {
                "site_info": {"dsn": brrts_id},
                "risk_flags": risk_from_docs.get('risk_flags', {}),
                "summary": response_text,
                "raw_response": response_text
            }
        
        # Merge document-based risk analysis
        if risk_from_docs:
            site_data['document_risk_analysis'] = risk_from_docs
        
        site_data['documents_analyzed'] = len(extracted_docs)
        site_data['documents'] = [
            {k: v for k, v in doc.items() if k != 'extracted_text'} 
            for doc in extracted_docs
        ]
        
        return jsonify(site_data)
        
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    AI-powered chat about site and selected documents.
    Extracts text from documents and uses it for comprehensive analysis.
    """
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    site_data = data.get("site_data") or {}
    selected_docs = data.get("selected_documents") or []
    history = data.get("history") or []
    session_id = data.get("session_id") or str(uuid.uuid4())
    
    if not question:
        return jsonify({"error": "Missing question."}), 400
    
    client = get_openrouter_client()
    
    if not client:
        site_info = site_data.get("site_info") or {}
        activity = site_info.get("activity_number", "(unknown)")
        status = site_info.get("status", "unknown")
        
        answer = (
            f"Site {activity} has status: {status}. "
            f"You selected {len(selected_docs)} document(s). "
            "AI analysis requires OPENROUTER_API_KEY in .env file.\n\n"
            f"Your question: {question}"
        )
        
        return jsonify({
            "answer": answer,
            "session_id": session_id,
            "history": history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer}
            ]
        })
    
    try:
        site_info = site_data.get("site_info") or {}
        risk_flags = site_data.get("risk_flags") or {}
        
        doc_summary = get_document_summary(selected_docs)
        
        # Check if documents already have extracted text (from frontend extraction)
        extracted_text = ""
        extraction_count = 0
        
        # First check if docs already have extracted text
        docs_with_text = [d for d in selected_docs if d.get('extracted_text')]
        
        if docs_with_text:
            # Use pre-extracted text
            text_parts = []
            for i, doc in enumerate(docs_with_text):
                doc_header = f"=== Document {i+1}: {doc.get('name', 'Unknown')} ({doc.get('date', 'No date')}) ===\n"
                text_parts.append(doc_header + doc['extracted_text'])
            combined_text = "\n\n".join(text_parts)
            extraction_count = len(docs_with_text)
            extracted_text = combined_text[:40000]
            if len(combined_text) > 40000:
                extracted_text += "\n\n[Document text truncated due to length...]"
        elif selected_docs and get_extraction_capabilities()['can_extract']:
            # Extract text fresh
            extracted_docs, combined_text = extract_all_documents(selected_docs, max_documents=10)
            extraction_count = sum(1 for d in extracted_docs if d.get('extraction_status') == 'success')
            
            if combined_text:
                # Truncate to reasonable size
                extracted_text = combined_text[:40000]
                if len(combined_text) > 40000:
                    extracted_text += "\n\n[Document text truncated due to length...]"
        
        # Build comprehensive system prompt with extracted document content
        doc_content_section = ""
        if extracted_text:
            doc_content_section = f"""

EXTRACTED DOCUMENT CONTENT ({extraction_count} documents successfully extracted):
{extracted_text}
"""
        
        system_prompt = f"""You are an environmental due diligence analyst helping a commercial real estate 
developer understand environmental risk for a Wisconsin property from BRRTS data.

SITE INFORMATION:
{json.dumps(site_info, indent=2)}

RISK INDICATORS:
{json.dumps(risk_flags, indent=2)}

SELECTED DOCUMENTS FOR REVIEW:
{doc_summary}
{doc_content_section}

Use this information to answer questions. Be specific about what the documents indicate.
Quote relevant sections from the documents when answering questions.
If you don't have enough information to answer, suggest what additional documents or 
investigations might help. Always recommend professional Phase I/II ESA review for legal decisions."""

        messages: list = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": question})
        
        # Use OpenRouter with a capable model
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            max_tokens=2048
        )
        answer = response.choices[0].message.content or "No response generated."
        
        updated_history = history + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ]
        
        return jsonify({
            "answer": answer,
            "session_id": session_id,
            "documents_processed": extraction_count,
            "history": updated_history
        })
        
    except Exception as e:
        error_msg = f"AI error: {str(e)}"
        return jsonify({
            "answer": error_msg,
            "session_id": session_id,
            "history": history
        }), 500


if __name__ == "__main__":
    # Check if we're in production (Railway/Render) or local development
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("PORT")
    debug_mode = False  # Disable debug mode to prevent auto-reloader issues with Playwright
    port = int(os.environ.get("PORT", 5000))
    
    print(f"=" * 50)
    print(f"Starting Cobalt AI Due Diligence Server")
    print(f"Port: {port}")
    print(f"Debug: {debug_mode}")
    print(f"Production: {is_production}")
    print(f"=" * 50)
    
    # Use threaded=True for better performance in production
    app.run(host="0.0.0.0", port=port, debug=debug_mode, threaded=True)
