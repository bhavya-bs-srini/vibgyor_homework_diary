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

# --- Path Config ---
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')
POPPLER_PATH = os.getenv('POPPLER_PATH', None)

# --- HELPER FUNCTIONS ---
def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    return re.sub(r'\s+', ' ', s).strip().title()

def is_nil(v):
    return bool(re.match(r'^(nil|nii|nls|nl|—|-|null|\.|n/a|bi|bs|by|ee|ca|we|cst|\s*)$', str(v).strip(), re.IGNORECASE))

def clean(v):
    v = re.sub(r'^[\[\|\\=_\-:\s]+', '', str(v))
    v = re.sub(r'[\[\|\\=_\-—~\s]+$', '', v)
    return v.strip()

def parse_date_str(s):
    for fmt in ['%d-%b-%y', '%d-%b-%Y', '%d.%m.%y', '%d.%m.%Y', '%d/%m/%y', '%d/%m/%Y']:
        try: return datetime.strptime(s.strip(), fmt)
        except: pass
    return None

def fmt(dt):
    return dt.strftime('%d-%b-%y') if hasattr(dt, 'strftime') else str(dt)

def extract_date_from_filename(fname):
    m = re.search(r'(\d{2})[._](\d{2})[._](\d{2,4})', fname)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def ocr_pdf(path):
    imgs = convert_from_path(path, dpi=200, poppler_path=POPPLER_PATH) # Lower DPI for speed
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(ImageOps.autocontrast(img.convert('L')), config='--psm 4 --oem 1') + '\n'
    return text

# --- CORE PROCESSING ---
def process_pdfs(pdf_paths):
    all_periods = []
    dates_found = []
    for path in pdf_paths:
        fname = os.path.basename(path)
        date_str = extract_date_from_filename(fname)
        if date_str:
            dt = parse_date_str(date_str)
            if dt: dates_found.append(dt)
        # Note: Ensure you have your `parse` and `consolidate` functions here
        # text = ocr_pdf(path)
        # all_periods += parse(text, date_str)
    
    week_monday = "Unknown"
    if dates_found:
        earliest = min(dates_found)
        mon = earliest - timedelta(days=earliest.weekday())
        week_monday = mon.strftime('%d-%b-%y')
        
    # Replace [] with your rows = consolidate(...) result
    return [], week_monday 

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