# Cobalt AI Due Diligence

Environmental risk analysis platform for Wisconsin BRRTS sites. Automatically extracts and analyzes DNR documents using AI.

## Features

- **Site Analysis**: Scrape site information from Wisconsin DNR BRRTS database
- **Document Extraction**: Auto-download and parse PDF documents
- **AI Summaries**: Generate comprehensive due diligence reports
- **Risk Analysis**: Identify PFAS, petroleum, metals, and other contamination

## Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/Cobalt-AI-Due-Diligence.git
cd Cobalt-AI-Due-Diligence
```

2. Create virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. (Optional) Install Playwright for full site scraping:
```bash
pip install playwright
playwright install chromium
```

4. Create `.env` file with your API key:
```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

5. Run the application:
```bash
python main.py
```

6. Open http://localhost:5000

## Deploying to Vercel

1. Push your code to GitHub

2. Go to [Vercel](https://vercel.com) and import your repository

3. Add environment variable in Vercel dashboard:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key

4. Deploy!

**Note**: On Vercel (serverless), Playwright is not available. The app will fall back to basic HTML scraping which may have limited data extraction. For full functionality, run locally.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | API key for AI features ([get one here](https://openrouter.ai/)) |
| `FLASK_SECRET_KEY` | No | Session secret key (auto-generated if not set) |
| `FLASK_DEBUG` | No | Set to "false" for production |

## Tech Stack

- **Backend**: Python Flask
- **Frontend**: HTML/CSS/JavaScript
- **AI**: OpenRouter (Gemini Flash)
- **PDF Parsing**: pypdf, pdfminer.six
- **Web Scraping**: Playwright (local), requests/BeautifulSoup (serverless)

## License

Proprietary - Cobalt Partners
