import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configuration for OCR and File Paths
POPPLER_PATH = os.environ.get('POPPLER_PATH', r"C:\poppler\poppler-26.02.0\Library\bin")
TESSERACT_CMD = os.environ.get('TESSERACT_CMD', r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

SKIP = {
    'assembly', 'spark', 'library', 'skill', 'enrichment',
    'language arts(support)', 'literature(support)',
    'math-support', 'math support', 'public speaking',
    'break', 'lunch', 'sports', 'pe', 'dance', 'music', 'yoga', 'meditation'
}

SUBJ_MAP = {
    'language arts': 'Language Arts',
    'literature': 'Literature',
    'ssc': 'SSC',
    'math': 'Math',
    'computer': 'Computer',
    '2nd language -hindi': '2ND LANGUAGE - Hindi',
    '2nd language -kannada': '2ND LANGUAGE - Kannada',
    '3rd language -hindi': '3RD LANGUAGE - Hindi',
    '3rd language -kannada': '3RD LANGUAGE - Kannada',
}

PAREN_CLEAN = re.compile(r'[\[\]_=\|\\,\(\)\-]+')

def norm_subj(s):
    lower = s.lower().strip()
    for k, v in SUBJ_MAP.items():
        if k in lower: return v
    return s.title()

def is_support(subj_raw):
    return '(support)' in subj_raw.lower() or ' support' in subj_raw.lower()

OCR_NOISE = re.compile(r'^(nil|nii|nls|nl|n|l|—|-|null|\.|n/a)$', re.IGNORECASE)

def is_nil(v):
    return not v or bool(OCR_NOISE.match(v.strip()))

def clean_val(v):
    return re.sub(r'^[\[\|\\=_\-:\s]+|[\[\|\\=_\-~\s]+$', '', str(v)).strip()

def clean_reinf(v):
    v = clean_val(v)
    return re.sub(r'^[^A-Za-z0-9]+|[-]+$', '', v).strip()

def parse_date_from_filename(basename):
    m = re.search(r'(\d{1,2})[_.](\d{1,2})[_.](\d{2,4})', basename)
    if not m: return datetime.today()
    d, m, y = m.groups()
    return datetime(int('20'+y if len(y)==2 else y), int(m), int(d))

def fmt_dt(dt):
    return dt.strftime('%d %b %Y')

def monday_of(dt):
    return dt - timedelta(days=dt.weekday())

def friday_of(mon_dt):
    return mon_dt + timedelta(days=4)

def next_monday(mon_dt):
    return mon_dt + timedelta(days=7)

def pdf_to_text(path):
    # Try pdfplumber first, fallback to OCR
    try:
        with pdfplumber.open(path) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            if len(text.strip()) > 100: return text
    except: pass
    
    # OCR fallback
    try:
        imgs = convert_from_path(path, dpi=300, poppler_path=POPPLER_PATH)
    except:
        imgs = convert_from_path(path, dpi=300)
    return '\n'.join(pytesseract.image_to_string(img) for img in imgs)

def parse(text, pdf_date_dt):
    periods = []
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^Period\s*[-:]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject'): periods.append(cur)
            cur = {'pdf_date': pdf_date_dt, 'subject': '', 'reinforcement': 'NIL'}
            continue
        if cur is None: continue
        
        m_subj = re.match(r'^Subject\s*(.*)', line, re.IGNORECASE)
        m_reinf = re.match(r'^Reinforce?ment\s*(.*)', line, re.IGNORECASE)
        
        if m_subj: cur['subject'] = norm_subj(clean_val(m_subj.group(1)))
        elif m_reinf: cur['reinforcement'] = clean_reinf(m_reinf.group(1))
            
    if cur and cur.get('subject'): periods.append(cur)
    return periods

def consolidate_by_week(all_periods):
    week_map = defaultdict(list)
    for p in all_periods:
        subj = p['subject']
        reinf = p['reinforcement']
        if not subj or subj.lower() in SKIP or is_nil(reinf): continue
        
        mon_dt = monday_of(p['pdf_date'])
        
        # Deadlines: Math = Fri of same week, Others = Mon of next week
        sub_dt = friday_of(mon_dt) if subj.lower() == 'math' else next_monday(mon_dt)
        
        week_map[mon_dt].append({
            'subject': subj,
            'reinf_date': fmt_dt(p['pdf_date']),
            'reinforcement': reinf,
            'submission': fmt_dt(sub_dt)
        })
    
    # Format for output
    output = []
    for mon_dt in sorted(week_map.keys()):
        output.append({'monday': fmt_dt(mon_dt), 'rows': week_map[mon_dt]})
    return output

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved_paths = []
    all_periods = []
    for f in files:
        path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
        f.save(path)
        saved_paths.append(path)
        all_periods += parse(pdf_to_text(path), parse_date_from_filename(f.filename))
    
    for p in saved_paths: os.remove(p)
    return jsonify({'weeks': consolidate_by_week(all_periods)})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)