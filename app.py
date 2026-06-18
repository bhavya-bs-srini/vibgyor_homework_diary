import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    'language arts': 'Language Arts', 'language art': 'Language Arts',
    'literature': 'Literature', 'ssc': 'SSC', 'math': 'Math', 'mathematics': 'Math',
    'art': 'Art', 'computer': 'Computer', 'robotics': 'Robotics',
    '2nd language -hindi': '2ND LANGUAGE - Hindi', '2nd ianguage -hindi': '2ND LANGUAGE - Hindi',
    '2nd language -kannada': '2ND LANGUAGE - Kannada', '2nd ianguage -kannada': '2ND LANGUAGE - Kannada',
    '3rd language -hindi': '3RD LANGUAGE - Hindi', '3rd language -kannada': '3RD LANGUAGE - Kannada'
}

PAREN_CLEAN = re.compile(r'[\[\]_=\|\\,\(\)\-]+')

def norm_subj(s):
    lower = s.lower().strip()
    for k, v in SUBJ_MAP.items():
        if lower == k or lower.startswith(k) or lower.endswith(k): return v
    return s.title()

def is_nil(v):
    return not v or bool(re.match(r'^(nil|nii|nls|nl|n|l|—|-|null|\.|\s*)$', v.strip(), re.IGNORECASE))

def clean_val(v): return re.sub(r'^[\[\|\\=_\-:\s]+|[\[\|\\=_\-~\s]+$', '', str(v)).strip()

def clean_reinf(v):
    v = re.sub(r'[-]+$', '', clean_val(v)).strip()
    return re.sub(r'^[^A-Za-z0-9]+', '', v)

def parse_date_from_filename(basename):
    m = re.search(r'(\d{1,2})[_.](\d{1,2})[_.](\d{2,4})', basename)
    if not m: return datetime.today()
    d, m, y = m.groups()
    return datetime(int('20'+y if len(y)==2 else y), int(m), int(d))

def fmt_dt(dt): return dt.strftime('%d %b %Y')
def monday_of(dt): return dt - timedelta(days=dt.weekday())
def friday_of(mon_dt): return mon_dt + timedelta(days=4)
def next_monday(mon_dt): return mon_dt + timedelta(days=7)

def ocr_image(img):
    return pytesseract.image_to_string(img.convert('L'), config='--psm 6 --oem 1')

def pdf_to_text(path):
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages: text += (page.extract_text() or '') + "\n"
    except:
        imgs = convert_from_path(path, dpi=300, poppler_path=POPPLER_PATH)
        for img in imgs: text += ocr_image(img) + "\n"
    return text

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

def process_single_pdf(path):
    return parse(pdf_to_text(path), parse_date_from_filename(os.path.basename(path)))

def consolidate_by_week(all_periods):
    week_map = defaultdict(lambda: defaultdict(list))
    for p in all_periods:
        if p['subject'].lower() in SKIP or is_nil(p['reinforcement']): continue
        mon = monday_of(p['pdf_date'])
        week_map[mon][p['subject']].append(p)
    
    output = []
    for mon in sorted(week_map.keys()):
        rows = []
        for subj, items in week_map[mon].items():
            rows.append({
                'subject': subj,
                'reinf_dates': [fmt_dt(i['pdf_date']) for i in items],
                'reinf_lines': [i['reinforcement'] for i in items],
                'submission': fmt_dt(friday_of(mon) if subj.lower() == 'math' else next_monday(mon))
            })
        output.append({'monday': fmt_dt(mon), 'friday': fmt_dt(friday_of(mon)), 'rows': rows})
    return output

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)
        with ProcessPoolExecutor() as executor:
            results = list(executor.map(process_single_pdf, saved))
        all_periods = [p for sublist in results for p in sublist]
        return jsonify({'weeks': consolidate_by_week(all_periods)})
    finally:
        for p in saved: os.remove(p)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000, debug=True)