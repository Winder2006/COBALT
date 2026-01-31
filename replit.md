# AI Due Diligence

Environmental Risk Analysis for Wisconsin BRRTS Sites

## Overview

This is an internal web application for a commercial real estate environmental team. It analyzes Wisconsin DNR BRRTS (Bureau for Remediation and Redevelopment Tracking System) data to assist with environmental due diligence.

**Purpose:** Help real estate developers quickly assess environmental risks for properties by fetching BRRTS data, scraping property documents, and generating AI-powered risk analysis.

**Current State:** Fully functional with document scraping and AI-powered Q&A. Requires OpenAI API key for AI features.

## Project Structure

```
.
├── main.py              # Flask app entry point with API endpoints
├── brrts_client.py      # Functions to fetch/parse Wisconsin DNR BRRTS data
├── document_scraper.py  # Playwright-based document scraper
├── risk_analysis.py     # OpenAI integration for risk analysis (legacy)
├── scraper1.py          # Original standalone scraper script
├── templates/
│   └── index.html       # Main UI template
├── static/
│   └── main.js          # Frontend JavaScript
├── requirements.txt     # Python dependencies
└── replit.md            # This file
```

## Key Features

1. **BRRTS Data Fetching**: Retrieves environmental activity data from Wisconsin DNR website
2. **Document Scraping**: Uses Playwright to extract document metadata from BRRTS pages
3. **Document Selection**: Users can select specific documents to analyze
4. **Risk Flag Analysis**: Identifies PFAS, petroleum, heavy metals, chlorinated solvents, etc.
5. **AI-Powered Q&A**: Ask questions about selected documents with GPT-5 context
6. **Interactive Chat**: Maintains conversation history for follow-up questions

## API Endpoints

- `GET /` - Main page
- `POST /api/analyze` - Analyze a BRRTS site (accepts `{"brrts": "588459"}`)
- `POST /api/documents` - Fetch documents for a site (accepts `{"dsn": "588459"}`)
- `POST /api/chat` - Chat about site and selected documents

## Tech Stack

- **Backend**: Python 3.11, Flask
- **HTTP Client**: requests
- **HTML Parsing**: BeautifulSoup4
- **Browser Automation**: Playwright (for document scraping)
- **AI**: OpenAI GPT-5 API

## Environment Variables

- `OPENAI_API_KEY` - Required for AI-powered Q&A. Without it, basic fallback responses are provided.

## Running the Application

```bash
python main.py
```

The application runs on port 5000.

## User Workflow

1. Enter a BRRTS activity ID (e.g., "588459") and click "Analyze Site"
2. Review site information, risk indicators, and summary
3. Click "Fetch Documents" to load available documents
4. Select documents you want to analyze by checking the boxes
5. Ask questions about the selected documents in the chat section
6. The AI will provide context-aware answers based on the document metadata

## Recent Changes

- **2025-12-16**: Added Playwright-based document scraping with user selection and AI-powered Q&A for selected documents
- **2025-12-02**: Initial implementation with BRRTS parsing and risk analysis
