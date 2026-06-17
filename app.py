import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
# On Render/Linux, /app/uploads is the standard path
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# Tesseract configuration for Render
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# --- 1. PASTE YOUR EXISTING HELPER FUNCTIONS HERE ---
# (e.g., norm_subj, is_nil, clean, parse_date_str, etc.)

def extract_date_from_filename(fname):
    m = re.search(r'(\d{2})[._](\d{2})[._](\d{2,4})', fname)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def ocr_pdf(path):
    # Reduced DPI to 200 for faster processing
    imgs = convert_from_path(path, dpi=200)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(ImageOps.autocontrast(img.convert('L')), config='--psm 4 --oem 1') + '\n'
    return text

# --- 2. PASTE YOUR 'parse' and 'consolidate' FUNCTIONS HERE ---
def parse(text, date):
    # INSERT YOUR ORIGINAL PARSE LOGIC HERE
    return []

def consolidate(all_periods):
    # INSERT YOUR ORIGINAL CONSOLIDATE LOGIC HERE
    return []

# --- 3. CORE PROCESSING LOGIC ---
def process_pdfs(pdf_paths):
    all_periods = []
    dates_found = []
    
    for path in pdf_paths:
        fname = os.path.basename(path)
        date_str = extract_date_from_filename(fname)
        if date_str:
            dt = datetime.strptime(date_str, '%d-%m-%Y') # Adjust format if needed
            if dt: dates_found.append(dt)
        
        # Process OCR
        text = ocr_pdf(path)
        all_periods += parse(text, date_str or 'Unknown')
    
    # Calculate Monday of the week
    week_monday = "Unknown"
    if dates_found:
        earliest = min(dates_found)
        mon = earliest - timedelta(days=earliest.weekday())
        week_monday = mon.strftime('%d-%b-%y')
        
    return consolidate(all_periods), week_monday

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        for f in files:
            if f and f.filename.lower().endswith('.pdf'):
                path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
                f.save(path)
                saved.append(path)
        
        rows, week = process_pdfs(saved)
        return jsonify({'success': True, 'rows': rows, 'week': week, 'files_processed': len(saved)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)