FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Increase timeout to 300 seconds (5 minutes) for OCR processing
CMD ["gunicorn", "app:app", "--timeout", "300", "--workers", "1"]