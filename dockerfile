FROM python:3.11-slim

# Only poppler needed now (no tesseract)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["gunicorn", "app:app", "--timeout", "120", "--workers", "1"]