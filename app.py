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
    'literature': 'Literature', 'ssc': 'SSC',
    'math': 'Math', 'mathematics': 'Math',
    'art': 'Art', 'computer': 'Computer', 'robotics': 'Robotics',
    '2nd language -hindi':    '2ND LANGUAGE - Hindi',
    '2nd ianguage -hindi':    '2ND LANGUAGE - Hindi',
    '2nd language - hindi':   '2ND LANGUAGE - Hindi',
    '2ndlanguage-hindi':      '2ND LANGUAGE - Hindi',
    '2nd language -kannada':  '2ND LANGUAGE - Kannada',
    '2nd ianguage -kannada':  '2ND LANGUAGE - Kannada',
    '2nd language - kannada': '2ND LANGUAGE - Kannada',
    '2ndlanguage-kannada':    '2ND LANGUAGE - Kannada',
    'kannada 2nd language':   '2ND LANGUAGE - Kannada',
    'kannada 2nd':            '2ND LANGUAGE - Kannada',
    '3rd language-hindi':     '3RD LANGUAGE - Hindi',
    '3rd language -hindi':    '3RD LANGUAGE - Hindi',
    '3rdlanguage-hindi':      '3RD LANGUAGE - Hindi',
    '3rd language - hindi':   '3RD LANGUAGE - Hindi',
    'srdlanguage-hindi':      '3RD LANGUAGE - Hindi',
    '3rd language-kannada':   '3RD LANGUAGE - Kannada',
    '3rdlanguage-kannada':    '3RD LANGUAGE - Kannada',
    '3rd language - kannada': '3RD LANGUAGE - Kannada',
    'srdlanguagekannada':     '3RD LANGUAGE - Kannada',
}

OCR_NOISE = re.compile(
    r'^(nil|nii|nls|nl|n|l|\xe2\x80\x94|—|-|null|\.|n/a|bi|bs|by|ee|ca|we|a|st|al|ose|kil|cst|sxt|\s*)$',
    re.IGNORECASE
)

def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    s = re.sub(r'\s+', ' ', s).strip()
    for k, v in SUBJ_MAP.items():
        if k in s:
            return v
    for k, v in SUBJ_MAP.items():
        if len(s) > 3 and (s in k or k.startswith(s[1:]) or k in s):
            return v
    return s.title()

def is_nil(v):
    if not v:
        return True
    return bool(OCR_NOISE.match(v.strip()))

def clean_val(v):
    v = re.sub(r'^[\[\|\\=_\-:\s]+', '', str(v))
    v = re.sub(r'[\[\|\\=_\-~\s]+$', '', v)
    return v.strip()

def clean_reinf(v):
    v = clean_val(v)
    v = re.sub(r'[-]+$', '', v).strip()
    v = re.sub(r'^[^A-Za-z0-9]+', '', v)
    return v

def parse_date_from_filename(basename):
    m = re.search(r'(\d{1,2})[_.](\d{1,2})[_.](\d{2,4})(?:\D|$)', basename)
    if not m:
        return None
    day, mon, yr = m.group(1), m.group(2), m.group(3)
    if len(yr) == 2:
        yr = '20' + yr
    try:
        return datetime(int(yr), int(mon), int(day))
    except ValueError:
        return None

def fmt_dt(dt):
    return dt.strftime('%-d %b %Y')

def monday_of(dt):
    return dt - timedelta(days=dt.weekday())

def friday_of(monday_dt):
    return monday_dt + timedelta(days=4)

def next_monday(monday_dt):
    return monday_dt + timedelta(days=7)

def extract_text(path):
    try:
        with pdfplumber.open(path) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
            if len(text.strip()) > 100:
                return True, text
    except Exception:
        pass
    return False, ''

def ocr_pdf(path):
    try:
        imgs = convert_from_path(path, dpi=300, poppler_path=POPPLER_PATH)
    except Exception:
        imgs = convert_from_path(path, dpi=300)
    text = ''
    for img in imgs:
        img2 = ImageOps.autocontrast(img.convert('L'))
        text += pytesseract.image_to_string(img2, config='--psm 4 --oem 1') + '\n'
    return text

def parse(text, pdf_date_dt):
    periods = []
    cur = None
    pending_header = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r'^(Sub\s*Topic|Topic|CW|Words\s+for|Additional|GROUP)', line, re.IGNORECASE):
            continue

        if re.match(r'^Period\s*[-:]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject'):
                periods.append(cur)
            cur = {'pdf_date': pdf_date_dt, 'subject': '', 'reinforcement': 'NIL'}
            pending_header = None
            continue

        if cur is None:
            continue

        m_subj  = re.match(r'^Subject\s*(.*)',        line, re.IGNORECASE)
        m_reinf = re.match(r'^Reinforce?ment\s*(.*)', line, re.IGNORECASE)

        if m_subj:
            val = clean_val(m_subj.group(1))
            if val:
                cur['subject'] = norm_subj(val)
            else:
                pending_header = 'subject'
            continue

        if m_reinf:
            val = clean_reinf(m_reinf.group(1))
            if val and not is_nil(val):
                cur['reinforcement'] = val
            else:
                pending_header = 'reinforcement'
            continue

        if pending_header:
            val = clean_val(line)
            if not is_nil(val):
                if pending_header == 'subject':
                    cur['subject'] = norm_subj(val)
                elif pending_header == 'reinforcement':
                    cur['reinforcement'] = val
            pending_header = None

    if cur and cur.get('subject'):
        periods.append(cur)
    return periods

def process_pdfs(pdf_paths):
    all_periods = []
    for path in pdf_paths:
        pdf_date_dt = parse_date_from_filename(os.path.basename(path)) or datetime.today()
        has_text, text = extract_text(path)
        if not has_text:
            text = ocr_pdf(path)
        all_periods += parse(text, pdf_date_dt)
    return all_periods

def consolidate_by_week(all_periods):
    week_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    seen = set()

    for p in all_periods:
        subj = p.get('subject', '').strip()
        if not subj or subj.lower() in SKIP or len(subj) < 2:
            continue

        reinf = p.get('reinforcement', '')
        if is_nil(reinf):
            continue

        pdf_dt   = p['pdf_date']
        mon_dt   = monday_of(pdf_dt)
        date_key = fmt_dt(pdf_dt)
        reinf    = clean_reinf(reinf)
        if is_nil(reinf):
            continue

        dedup = (mon_dt, subj, reinf, date_key)
        if dedup in seen:
            continue
        seen.add(dedup)
        week_data[mon_dt][subj][date_key].append(reinf)

    def sort_date_key(ds):
        for f in ('%-d %b %Y', '%d %b %Y'):
            try: return datetime.strptime(ds, f)
            except: pass
        return datetime.min

    weeks = []
    for mon_dt in sorted(week_data):
        fri_dt     = friday_of(mon_dt)
        nxt_mon_dt = next_monday(mon_dt)
        subj_map   = week_data[mon_dt]
        rows = []
        for subj in sorted(subj_map):
            dates_sorted = sorted(subj_map[subj].keys(), key=sort_date_key)
            reinf_dates  = dates_sorted
            reinf_lines  = [', '.join(subj_map[subj][d]) for d in dates_sorted]
            submission   = fmt_dt(fri_dt) if subj.lower() == 'math' else fmt_dt(nxt_mon_dt)
            rows.append({
                'subject':     subj,
                'reinf_dates': reinf_dates,
                'reinf_lines': reinf_lines,
                'submission':  submission,
            })
        weeks.append({
            'monday': fmt_dt(mon_dt),
            'friday': fmt_dt(fri_dt),
            'rows':   rows,
        })
    return weeks

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)

        all_periods = process_pdfs(saved)
        weeks = consolidate_by_week(all_periods)

        return jsonify({'success': True, 'weeks': weeks, 'files_processed': len(saved)})

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500
    finally:
        for p in saved:
            if os.path.exists(p):
                os.remove(p)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)