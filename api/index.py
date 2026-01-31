from flask import Flask, Response
import os

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
    
    # Return basic info - full scraping not available on serverless
    return jsonify({
        "site_info": {
            "dsn": dsn,
            "activity_number": f"XX-XX-{dsn}",
        },
        "risk_flags": {"status_label": "UNKNOWN"},
        "summary": f"Site {dsn} loaded. Note: Full scraping requires local deployment with Playwright.",
        "documents_available": 0
    })

@app.route("/api/documents", methods=["POST"])
def api_documents():
    from flask import request, jsonify
    data = request.get_json() or {}
    dsn = (data.get("dsn") or "").strip()
    
    # Provide manual document option
    return jsonify({
        "documents": [],
        "count": 0,
        "extraction_available": True,
        "note": "Add documents manually using docSeqNo from DNR site"
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
                except:
                    doc["extraction_status"] = "failed"
            else:
                doc["extraction_status"] = "download_failed"
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
    
    if not combined_text:
        return jsonify({"error": "No text to summarize."}), 400
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENROUTER_API_KEY not set."}), 400
    
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": "You are an environmental due diligence analyst."},
                {"role": "user", "content": f"Summarize this environmental site document:\n\n{combined_text[:30000]}"}
            ],
            max_tokens=2000
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
    
    if not question:
        return jsonify({"error": "No question."}), 400
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return jsonify({"answer": "AI requires OPENROUTER_API_KEY.", "history": []})
    
    # Get any extracted text
    doc_text = "\n\n".join(d.get("extracted_text", "")[:10000] for d in selected_docs if d.get("extracted_text"))
    
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {"role": "system", "content": f"Environmental analyst. Document context:\n{doc_text[:20000]}"},
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
