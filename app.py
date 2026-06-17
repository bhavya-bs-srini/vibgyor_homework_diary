import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# --- Core Helper Functions ---
def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    return re.sub(r'\s+', ' ', s).strip().title()

def extract_date_from_filename(fname):
    m = re.search(r'(\d{2})[._](\d{2})[._](\d{2,4})', fname)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

def parse_date_str(s):
    for fmt in ['%d-%b-%y', '%d-%b-%Y', '%d.%m.%y', '%d.%m.%Y', '%d/%m/%y', '%d/%m/%Y']:
        try: return datetime.strptime(s.strip(), fmt)
        except: continue
    return None

def ocr_pdf(path):
    # Using 200 DPI for faster processing
    imgs = convert_from_path(path, dpi=200)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(ImageOps.autocontrast(img.convert('L')), config='--psm 4 --oem 1') + '\n'
    return text

def parse_pdf_content(text, date_str):
    # YOUR ORIGINAL PARSE LOGIC GOES HERE
    # This must return a list of dicts: [{'subject': '...', 'reinforcement': '...', 'submission': '...'}]
    return []

def consolidate_data(all_periods):
    # YOUR ORIGINAL CONSOLIDATE LOGIC GOES HERE
    # This must return a list of dicts: [{'subject': '...', 'reinf_dates': [...], 'reinf_lines': [...], 'submission': '...'}]
    return []

def process_pdfs(pdf_paths):
    all_periods = []
    dates_found = []
    for path in pdf_paths:
        fname = os.path.basename(path)
        date_str = extract_date_from_filename(fname)
        if date_str:
            dt = parse_date_str(date_str)
            if dt: dates_found.append(dt)
        
        text = ocr_pdf(path)
        all_periods += parse_pdf_content(text, date_str)
    
    # Calculate Monday of the week
    week_monday = "Unknown"
    if dates_found:
        earliest = min(dates_found)
        mon = earliest - timedelta(days=earliest.weekday())
        week_monday = mon.strftime('%d-%b-%y')
        
    return consolidate_data(all_periods), week_monday

# --- Routes ---
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