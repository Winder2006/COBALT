from __future__ import annotations

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict
import requests


def _derive_filename(response: requests.Response, fallback: Optional[str] = None) -> str:
    """Infer filename from response headers, fall back when missing."""
    header = response.headers.get("Content-Disposition", "")
    parts = header.split("filename=")
    if len(parts) > 1:
        candidate = parts[1].strip('"; ')
        if candidate:
            return candidate
    return fallback or "downloaded_document.pdf"


def _unique_path(dest_dir: Path, name: str) -> Path:
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        new_candidate = dest_dir / f"{stem}_{counter}{suffix}"
        if not new_candidate.exists():
            return new_candidate
        counter += 1


def download_file(url: str, dest_dir: Optional[Path] = None, filename: Optional[str] = None) -> Path:
    """Download a single file and return the saved path."""
    dest_dir = Path(dest_dir or Path(__file__).parent).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    with requests.get(url, allow_redirects=True, stream=True, timeout=120) as response:
        response.raise_for_status()
        target_name = filename or _derive_filename(response)
        target_path = _unique_path(dest_dir, target_name)
        with target_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)

    return target_path


class DocumentSession:
    """Manages a temporary session for downloading and storing documents."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.base_dir = Path(tempfile.gettempdir()) / "brrts_documents" / session_id
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.downloaded_files: Dict[str, Path] = {}
    
    def download_document(self, doc: Dict) -> Optional[Path]:
        """Download a single document and return the file path."""
        url = doc.get("download_url")
        if not url:
            return None
        
        doc_id = doc.get("id") or url
        
        if doc_id in self.downloaded_files:
            return self.downloaded_files[doc_id]
        
        try:
            filename = doc.get("name", "document.pdf")
            filename = filename.replace("/", "_").replace("\\", "_")
            
            file_path = download_file(url, self.base_dir, filename)
            self.downloaded_files[doc_id] = file_path
            return file_path
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None
    
    def download_documents(self, documents: List[Dict]) -> List[Path]:
        """Download multiple documents and return list of file paths."""
        paths = []
        for doc in documents:
            path = self.download_document(doc)
            if path:
                paths.append(path)
        return paths
    
    def get_downloaded_paths(self) -> List[Path]:
        """Get all downloaded file paths."""
        return list(self.downloaded_files.values())
    
    def cleanup(self):
        """Remove all downloaded files for this session."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir, ignore_errors=True)
        self.downloaded_files.clear()


_sessions: Dict[str, DocumentSession] = {}


def get_or_create_session(session_id: str) -> DocumentSession:
    """Get existing session or create a new one."""
    if session_id not in _sessions:
        _sessions[session_id] = DocumentSession(session_id)
    return _sessions[session_id]


def cleanup_session(session_id: str):
    """Clean up a session and remove its files."""
    if session_id in _sessions:
        _sessions[session_id].cleanup()
        del _sessions[session_id]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download a single document from RR BOTW.")
    parser.add_argument("url", help="Document download URL")
    parser.add_argument("--output-dir", default=".", help="Directory where the file should be saved.")
    parser.add_argument("--filename", help="Optional filename override for the saved file.")
    args = parser.parse_args()

    saved = download_file(args.url, Path(args.output_dir), args.filename)
    print(f"File saved successfully: {saved}")
