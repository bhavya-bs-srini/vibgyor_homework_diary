import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
# Use absolute path for Render compatibility
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# --- CONFIGS & LOGIC (Restored from app_old.py) ---
SKIP = {'assembly', 'spark', 'library', 'skill', 'enrichment', 'language arts(support)', 'literature(support)', 'math-support', 'math support', 'public speaking'}
SUBJ_MAP = {'language arts': 'Language Arts', 'language art': 'Language Arts', 'literature': 'Literature', 'ssc': 'SSC', 'math': 'Math', 'mathematics': 'Math', 'art': 'Art', 'computer': 'Computer', 'robotics': 'Robotics', '2nd language -hindi': '2ND LANGUAGE - Hindi', '2nd ianguage -hindi': '2ND LANGUAGE - Hindi', '2nd language - hindi': '2ND LANGUAGE - Hindi', '2ndlanguage-hindi': '2ND LANGUAGE - Hindi', '2nd language -kannada': '2ND LANGUAGE - Kannada', '2nd ianguage -kannada': '2ND LANGUAGE - Kannada', '2nd language - kannada': '2ND LANGUAGE - Kannada', '2ndlanguage-kannada': '2ND LANGUAGE - Kannada', 'kannada 2nd language': '2ND LANGUAGE - Kannada', 'kannada 2nd': '2ND LANGUAGE - Kannada', '3rd language-hindi': '3RD LANGUAGE - Hindi', '3rd language -hindi': '3RD LANGUAGE - Hindi', '3rdlanguage-hindi': '3RD LANGUAGE - Hindi', '3rd language - hindi': '3RD LANGUAGE - Hindi', 'srdlanguage-hindi': '3RD LANGUAGE - Hindi', '3rd language-kannada': '3RD LANGUAGE - Kannada', '3rdlanguage-kannada': '3RD LANGUAGE - Kannada', '3rd language - kannada': '3RD LANGUAGE - Kannada', 'srdlanguagekannada': '3RD LANGUAGE - Kannada'}

def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return SUBJ_MAP.get(s, s.title())

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

def fmt(dt): return dt.strftime('%-d %b %Y') if hasattr(dt, 'strftime') else str(dt)

def parse(text, date):
def parse(text, date):
    periods, cur = [], None
    # Track state: if we just saw a header, capture the next line's value
    pending_header = None 
    
    for line in text.splitlines():
        line = line.strip()
        if not line or re.match(r'^(Sub\s*Topic|Topic|CW|Words\s+for|Additional|GROUP)', line, re.IGNORECASE): 
            continue
        
        # 1. Capture Headers that might have values on next lines
        m_subj = re.match(r'^Subject\s*(.*)', line, re.IGNORECASE)
        m_reinf = re.match(r'^Reinforce?ment\s*(.*)', line, re.IGNORECASE)
        m_subm = re.match(r'^Submission\s*date?\s*(.*)', line, re.IGNORECASE)
        
        # Handle "Period" start
        if re.match(r'^Period\s*[-–]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject'): periods.append(cur)
            cur = {'date': date, 'subject': '', 'reinforcement': 'NIL', 'submission': 'NIL'}
            pending_header = None
            continue
        
        # Capture logic for headers
        if m_subj:
            val = clean(m_subj.group(1))
            if val: cur['subject'] = norm_subj(val)
            else: pending_header = 'subject'
            continue
        if m_reinf:
            val = clean(m_reinf.group(1))
            if val: cur['reinforcement'] = val
            else: pending_header = 'reinforcement'
            continue
        if m_subm:
            val = clean(m_subm.group(1))
            if val: cur['submission'] = val
            else: pending_header = 'submission'
            continue
            
        # 2. If we were waiting for a header value, capture it now
        if pending_header and cur is not None:
            val = clean(line)
            if not is_nil(val):
                if pending_header == 'subject': cur['subject'] = norm_subj(val)
                elif pending_header == 'reinforcement': cur['reinforcement'] = val
                elif pending_header == 'submission': cur['submission'] = val
            pending_header = None
            continue

    if cur and cur.get('subject'): periods.append(cur)
    return periods

def ocr_pdf(path):
    imgs = convert_from_path(path, dpi=200)
    text = ''
    for img in imgs: text += pytesseract.image_to_string(ImageOps.autocontrast(img.convert('L')), config='--psm 4 --oem 1') + '\n'
    return text

def consolidate(all_periods, friday_str, nxt_monday_str):
    subj_date, subj_sub, seen = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: 'NIL'), set()
    for p in all_periods:
        subj = p.get('subject', '').strip()
        if not subj or subj.lower() in SKIP or len(subj) < 2: continue
        if not is_nil(p.get('reinforcement')):
            key = (subj, p.get('reinforcement'), p.get('date'))
            if key not in seen:
                seen.add(key); subj_date[subj][p.get('date', '')].append(p.get('reinforcement'))
        if not is_nil(p.get('submission')) and subj_sub[subj] == 'NIL': subj_sub[subj] = p.get('submission')
    rows = []
    for subj in sorted(subj_date):
        dates = sorted(subj_date[subj])
        reinf_dates = [fmt(parse_date_str(d)) if parse_date_str(d) else d for d in dates]
        reinf_lines = [', '.join(subj_date[subj][d]) for d in dates]
        submission = (fmt(parse_date_str(subj_sub[subj])) if parse_date_str(subj_sub[subj]) else subj_sub[subj]) if subj_sub[subj] != 'NIL' else (friday_str if subj == 'Math' else nxt_monday_str)
        rows.append({'subject': subj, 'reinf_dates': reinf_dates, 'reinf_lines': reinf_lines, 'submission': submission})
    return rows

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path); saved.append(path)
        
        all_periods, dates_seen = [], []
        for path in saved:
            # Simple extraction from filename for date
            m = re.search(r'(\d{2})[._](\d{2})[._](\d{2,4})', os.path.basename(path))
            date_hint = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            if date_hint: dates_seen.append(date_hint)
            
            # Extract text (using OCR directly for consistency)
            text = ocr_pdf(path)
            all_periods += parse(text, date_hint or 'Unknown')
        
        monday_dt = None
        if dates_seen:
            d = parse_date_str(dates_seen[0])
            if d: monday_dt = d - timedelta(days=d.weekday())
        
        friday = fmt(monday_dt + timedelta(days=4)) if monday_dt else 'Unknown'
        nxt_mon = fmt(monday_dt + timedelta(days=7)) if monday_dt else 'Unknown'
        
        rows = consolidate(all_periods, friday, nxt_mon)
        return jsonify({'success': True, 'rows': rows, 'week': fmt(monday_dt) if monday_dt else 'Unknown', 'files_processed': len(saved)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)