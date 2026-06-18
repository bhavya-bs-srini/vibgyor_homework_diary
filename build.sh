#!/usr/bin/env bash
set -e  # Exit on error

# Install system dependencies
apt-get install -y poppler-utils tesseract-ocr

# Install Python dependencies
pip install -r requirements.txt