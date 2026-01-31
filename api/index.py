"""
Vercel Serverless Function Entry Point
"""
from flask import Flask, render_template, request, jsonify, session
import os
import sys
import json
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Create Flask app with correct template/static paths
template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['JSON_SORT_KEYS'] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "vercel-secret-key-change-me")


def get_openrouter_client():
    """Create OpenAI client configured for OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


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
    """Analyze a BRRTS site."""
    data = request.get_json() or {}
    brrts_id = (data.get("brrts") or "").strip()
    
    if not brrts_id:
        return jsonify({"error": "Missing BRRTS activity ID."}), 400
    
    digits_only = ''.join(c for c in brrts_id if c.isdigit())
    dsn = digits_only[-6:] if len(digits_only) >= 6 else digits_only
    
    try:
        # Import here to avoid issues if module not available
        from document_scraper import extract_site_and_documents
        result = extract_site_and_documents(dsn)
        
        return jsonify({
            "site_info": result.get("site_info", {"dsn": dsn}),
            "risk_flags": result.get("risk_flags", {"status_label": "UNKNOWN"}),
            "summary": result.get("summary", "Site data loaded."),
            "documents_available": len(result.get("documents", []))
        })
    except Exception as e:
        return jsonify({
            "site_info": {"dsn": dsn},
            "risk_flags": {"status_label": "UNKNOWN"},
            "summary": f"Analysis running in limited mode: {str(e)}",
            "error": str(e)
        })


@app.route("/api/documents", methods=["POST"])
def api_documents():
    """Fetch documents for a BRRTS site."""
    data = request.get_json() or {}
    dsn = (data.get("dsn") or "").strip()
    
    if not dsn:
        return jsonify({"error": "Missing DSN."}), 400
    
    try:
        from document_scraper import extract_site_and_documents
        result = extract_site_and_documents(dsn)
        documents = result.get("documents", [])
        
        return jsonify({
            "documents": documents,
            "count": len(documents),
            "extraction_available": True
        })
    except Exception as e:
        return jsonify({
            "documents": [],
            "error": str(e)
        })


@app.route("/api/documents/add", methods=["POST"])
def api_add_document():
    """Manually add a document by docSeqNo."""
    data = request.get_json() or {}
    doc_seq_no = (data.get("docSeqNo") or "").strip()
    doc_url = (data.get("url") or "").strip()
    
    if not doc_seq_no and not doc_url:
        return jsonify({"error": "Missing docSeqNo or URL."}), 400
    
    download_url = f"https://apps.dnr.wi.gov/rrbotw/download-document?docSeqNo={doc_seq_no}&sender=activity" if doc_seq_no else doc_url
    
    document = {
        "id": 0,
        "download_url": download_url,
        "category": "Site File",
        "date": "",
        "action_code": "",
        "name": f"Site File Documentation (ID: {doc_seq_no or 'Manual'})",
        "comment": "Manually added document",
    }
    
    return jsonify({"document": document, "success": True})


@app.route("/api/documents/extract", methods=["POST"])
def api_extract_documents():
    """Extract text from documents."""
    data = request.get_json() or {}
    documents = data.get("documents") or []
    
    if not documents:
        return jsonify({"error": "No documents provided."}), 400
    
    try:
        from pdf_extractor import extract_all_documents, analyze_extracted_text_for_risks
        
        extracted_docs, combined_text = extract_all_documents(documents, max_documents=20)
        risk_analysis = analyze_extracted_text_for_risks(combined_text)
        successful = sum(1 for d in extracted_docs if d.get('extraction_status') == 'success')
        
        return jsonify({
            "documents": extracted_docs,
            "combined_text": combined_text[:50000] if combined_text else "",
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


@app.route("/api/documents/summarize", methods=["POST"])
def api_summarize_documents():
    """Generate AI summary of documents."""
    data = request.get_json() or {}
    combined_text = data.get("combined_text", "")
    site_data = data.get("site_data", {})
    
    if not combined_text:
        return jsonify({"error": "No document text to summarize."}), 400
    
    client = get_openrouter_client()
    if not client:
        return jsonify({"error": "OPENROUTER_API_KEY not configured."}), 400
    
    try:
        site_info = site_data.get("site_info", {})
        truncated_text = combined_text[:35000]
        
        prompt = f"""Analyze these environmental site documents for: {site_info.get('location_name', 'Unknown Site')}

DOCUMENT TEXT:
{truncated_text}

Provide a due diligence summary including:
1. Site Overview
2. Contamination Summary  
3. Remediation Status
4. Key Risk Factors
5. Recommendations"""

        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": "You are an environmental due diligence analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000
        )
        
        return jsonify({
            "summary": response.choices[0].message.content or "No summary generated.",
            "text_length": len(combined_text)
        })
    except Exception as e:
        return jsonify({"error": f"AI summarization failed: {str(e)}"}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """AI chat about documents."""
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
        return jsonify({
            "answer": "AI features require OPENROUTER_API_KEY environment variable.",
            "session_id": session_id,
            "history": history
        })
    
    try:
        site_info = site_data.get("site_info", {})
        
        # Get extracted text from docs if available
        extracted_text = ""
        docs_with_text = [d for d in selected_docs if d.get('extracted_text')]
        if docs_with_text:
            text_parts = [d['extracted_text'] for d in docs_with_text[:5]]
            extracted_text = "\n\n".join(text_parts)[:40000]
        
        system_prompt = f"""You are an environmental due diligence analyst.
        
Site: {json.dumps(site_info, indent=2)}

Document Text:
{extracted_text[:30000] if extracted_text else 'No documents extracted yet.'}

Answer questions about this environmental site."""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-10:])  # Last 10 messages
        messages.append({"role": "user", "content": question})
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            max_tokens=2048
        )
        
        answer = response.choices[0].message.content or "No response."
        
        return jsonify({
            "answer": answer,
            "session_id": session_id,
            "history": history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer}
            ]
        })
    except Exception as e:
        return jsonify({
            "answer": f"Error: {str(e)}",
            "session_id": session_id,
            "history": history
        })


# For Vercel
app = app
