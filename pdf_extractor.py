"""
PDF Text Extraction Module
--------------------------
Downloads and extracts text content from Wisconsin DNR BRRTS documents.
"""

import io
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    from pdfminer.pdfparser import PDFSyntaxError
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False


def download_pdf_content(url: str, timeout: int = 60) -> Optional[bytes]:
    """
    Download PDF content from URL.
    
    Args:
        url: The URL to download from
        timeout: Request timeout in seconds
        
    Returns:
        PDF bytes or None if download failed
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' in content_type or url.lower().endswith('.pdf') or len(response.content) > 1000:
            return response.content
        return None
    except Exception as e:
        print(f"Error downloading PDF from {url}: {e}")
        return None


def extract_text_pypdf(pdf_content: bytes) -> str:
    """Extract text using pypdf library."""
    if not PYPDF_AVAILABLE:
        return ""
    
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_content))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"pypdf extraction error: {e}")
        return ""


def extract_text_pdfminer(pdf_content: bytes) -> str:
    """Extract text using pdfminer.six library."""
    if not PDFMINER_AVAILABLE:
        return ""
    
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(pdf_content)
            tmp_path = tmp.name
        
        text = pdfminer_extract(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        return text or ""
    except PDFSyntaxError:
        return ""
    except Exception as e:
        print(f"pdfminer extraction error: {e}")
        return ""


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text from PDF content using available libraries.
    Tries pypdf first, falls back to pdfminer.
    
    Args:
        pdf_content: Raw PDF bytes
        
    Returns:
        Extracted text string
    """
    text = ""
    
    # Try pypdf first (faster)
    if PYPDF_AVAILABLE:
        text = extract_text_pypdf(pdf_content)
    
    # Fall back to pdfminer if pypdf failed or not available
    if not text.strip() and PDFMINER_AVAILABLE:
        text = extract_text_pdfminer(pdf_content)
    
    return clean_extracted_text(text)


def clean_extracted_text(text: str) -> str:
    """Clean up extracted PDF text."""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' +\n', '\n', text)
    
    # Remove common PDF artifacts
    text = re.sub(r'\x00', '', text)
    
    return text.strip()


def extract_document_text(doc: Dict) -> Dict:
    """
    Download a document and extract its text.
    
    Args:
        doc: Document metadata dict with 'download_url' key
        
    Returns:
        Document dict with added 'extracted_text' and 'extraction_status' keys
    """
    url = doc.get('download_url')
    result = doc.copy()
    result['extracted_text'] = ""
    result['extraction_status'] = "no_url"
    
    if not url:
        return result
    
    # Download PDF
    pdf_content = download_pdf_content(url)
    if not pdf_content:
        result['extraction_status'] = "download_failed"
        return result
    
    # Extract text
    text = extract_text_from_pdf(pdf_content)
    if text:
        result['extracted_text'] = text
        result['extraction_status'] = "success"
        result['text_length'] = len(text)
    else:
        result['extraction_status'] = "extraction_failed"
    
    return result


def extract_all_documents(documents: List[Dict], max_documents: int = 50) -> Tuple[List[Dict], str]:
    """
    Extract text from all documents.
    
    Args:
        documents: List of document metadata dicts
        max_documents: Maximum number of documents to process
        
    Returns:
        Tuple of (documents with extracted text, combined text summary)
    """
    results = []
    all_text_parts = []
    
    for i, doc in enumerate(documents[:max_documents]):
        result = extract_document_text(doc)
        results.append(result)
        
        if result.get('extracted_text'):
            doc_header = f"=== Document {i+1}: {doc.get('name', 'Unknown')} ({doc.get('date', 'No date')}) ===\n"
            all_text_parts.append(doc_header + result['extracted_text'])
    
    combined_text = "\n\n" + "="*80 + "\n\n".join(all_text_parts) if all_text_parts else ""
    
    return results, combined_text


def analyze_extracted_text_for_risks(text: str) -> Dict:
    """
    Analyze extracted text for environmental risk indicators.
    
    Args:
        text: Combined extracted text from all documents
        
    Returns:
        Dict with risk flags and extracted information
    """
    text_lower = text.lower()
    
    # Contaminant detection
    pfas_keywords = ['pfas', 'pfoa', 'pfos', 'perfluor', 'forever chemical']
    petroleum_keywords = ['petroleum', 'gasoline', 'diesel', 'btex', 'benzene', 'toluene', 
                         'ethylbenzene', 'xylene', 'fuel oil', 'heating oil', 'ust ', 
                         'underground storage tank', 'lust', 'leaking underground']
    metals_keywords = ['arsenic', 'lead', 'chromium', 'mercury', 'cadmium', 'heavy metal',
                      'metals contamination']
    chlorinated_keywords = ['tce', 'pce', 'chlorinated', 'trichloroethylene', 'tetrachloroethylene',
                           'vinyl chloride', 'dce', 'solvent']
    
    # Status detection
    closure_keywords = ['case closed', 'no further action', 'nfa', 'closure', 'closed']
    open_keywords = ['open case', 'ongoing', 'active remediation', 'monitoring required']
    
    # Impact detection
    offsite_keywords = ['off-site', 'offsite', 'migrated', 'plume', 'groundwater impact',
                       'vapor intrusion', 'neighboring property']
    groundwater_keywords = ['groundwater', 'aquifer', 'well contamination', 'drinking water']
    soil_keywords = ['soil contamination', 'contaminated soil', 'soil vapor']
    
    # Extract findings
    risks = {
        'pfas': any(kw in text_lower for kw in pfas_keywords),
        'petroleum': any(kw in text_lower for kw in petroleum_keywords),
        'heavy_metals': any(kw in text_lower for kw in metals_keywords),
        'chlorinated_solvents': any(kw in text_lower for kw in chlorinated_keywords),
        'offsite_impact': any(kw in text_lower for kw in offsite_keywords),
        'groundwater_impact': any(kw in text_lower for kw in groundwater_keywords),
        'soil_contamination': any(kw in text_lower for kw in soil_keywords),
    }
    
    # Try to determine status from documents
    has_closure = any(kw in text_lower for kw in closure_keywords)
    has_open = any(kw in text_lower for kw in open_keywords)
    
    if has_closure and not has_open:
        status = "CLOSED"
    elif has_open:
        status = "OPEN"
    else:
        status = "UNKNOWN"
    
    # Extract any concentration values (basic pattern matching)
    concentration_pattern = r'(\d+(?:\.\d+)?)\s*(ppb|ppm|mg/l|ug/l|mg/kg)'
    concentrations = re.findall(concentration_pattern, text_lower)
    
    return {
        'risk_flags': risks,
        'inferred_status': status,
        'concentrations_found': len(concentrations),
        'document_text_length': len(text),
    }


# Check which libraries are available
def get_extraction_capabilities() -> Dict:
    """Return information about available extraction capabilities."""
    return {
        'pypdf_available': PYPDF_AVAILABLE,
        'pdfminer_available': PDFMINER_AVAILABLE,
        'can_extract': PYPDF_AVAILABLE or PDFMINER_AVAILABLE,
    }


if __name__ == "__main__":
    caps = get_extraction_capabilities()
    print(f"PDF Extraction Capabilities: {caps}")
    
    if not caps['can_extract']:
        print("\nWARNING: No PDF extraction library available!")
        print("Install one of: pypdf, pdfminer.six")
