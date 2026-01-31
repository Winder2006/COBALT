"""
Install Playwright browsers on startup.
Run this before the main app to ensure browsers are available.
"""
import subprocess
import sys
import os

def install_playwright_browsers():
    """Install Playwright Chromium browser."""
    print("Installing Playwright browsers...")
    
    try:
        # Install using Python -m playwright install
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            print("Playwright Chromium installed successfully!")
            print(result.stdout)
        else:
            print(f"Playwright install failed with code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            
            # Try installing dependencies too
            print("Trying to install system dependencies...")
            dep_result = subprocess.run(
                [sys.executable, "-m", "playwright", "install-deps", "chromium"],
                capture_output=True,
                text=True,
                timeout=300
            )
            print(f"Dependencies install: {dep_result.returncode}")
            print(dep_result.stdout)
            print(dep_result.stderr)
            
    except Exception as e:
        print(f"Error installing Playwright: {e}")

if __name__ == "__main__":
    install_playwright_browsers()
