# Use official Playwright image - browsers pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Tell Playwright to skip browser download - they're already installed
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Environment
ENV PYTHONUNBUFFERED=1

# Start Flask directly
CMD ["python", "main.py"]
