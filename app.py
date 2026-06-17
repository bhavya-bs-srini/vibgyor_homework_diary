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
POPPLER_PATH = os.getenv('POPPLER_PATH', None) # None for Linux/Render

# --- ALL YOUR HELPER FUNCTIONS ---
def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return s.title()

def is_nil(v):
    if not v: return True
    return bool(re.match(r'^(nil|nii|nls|nl|—|-|null|\.|n/a|bi|bs|by|ee|ca|we|cst|\s*)$', v.strip(), re.IGNORECASE))

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
    return dt.strftime('%-d %b %Y') if hasattr(dt, 'strftime') else str(dt)

def parse(text, date):
    periods, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if re.match(r'^Period\s*[-–]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject'): periods.append(cur)
            cur = {'date': date, 'subject': '', 'reinforcement': 'NIL', 'submission': 'NIL'}
            continue
        m = re.match(r'^Subject\s+(.+)', line, re.IGNORECASE)
        if m:
            subj = norm_subj(clean(m.group(1)))
            if cur and cur.get('subject'): periods.append(cur)
            cur = {'date': date, 'subject': subj, 'reinforcement': 'NIL', 'submission': 'NIL'}
            continue
        if cur is None: continue
        m = re.match(r'^Reinforce?ment\s*(.*)', line, re.IGNORECASE)
        if m:
            val = clean(m.group(1))
            if val and not is_nil(val): cur['reinforcement'] = val
        m = re.match(r'^Submission\s*date?\s*(.*)', line, re.IGNORECASE)
        if m:
            val = clean(m.group(1))
            if val and not is_nil(val): cur['submission'] = val
    if cur and cur.get('subject'): periods.append(cur)
    return periods

def ocr_pdf(path):
    imgs = convert_from_path(path, dpi=400, poppler_path=POPPLER_PATH)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(ImageOps.autocontrast(img.convert('L')), config='--psm 4 --oem 1') + '\n'
    return text

def process_pdfs(pdf_paths):
    all_periods = []
    # (Simplified example: insert your full consolidation logic here)
    for path in pdf_paths:
        text = ocr_pdf(path)
        all_periods += parse(text, '17-Jun-26') # Ensure you use the dynamic date extraction
    
    # Return formatted rows as expected by your HTML
    return [], "17-Jun-26" 

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)
        rows, week_monday = process_pdfs(saved)
        return jsonify({'success': True, 'rows': rows, 'week': week_monday, 'files_processed': len(saved)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000)