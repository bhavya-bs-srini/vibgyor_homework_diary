import os, re, uuid
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

SKIP = {
    'assembly', 'spark', 'library', 'skill', 'enrichment',
    'language arts(support)', 'literature(support)',
    'math-support', 'math support', 'public speaking'
}

SUBJ_MAP = {
    'language arts':          'Language Arts',
    'language art':           'Language Arts',
    'literature':             'Literature',
    'ssc':                    'SSC',
    'math':                   'Math',
    'mathematics':            'Math',
    'art':                    'Art',
    'computer':               'Computer',
    'robotics':               'Robotics',
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

def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    s = re.sub(r'\s+', ' ', s).strip()
    for k, v in SUBJ_MAP.items():
        if k in s: return v
    return s.title()

def is_nil(v):
    if not v: return True
    return bool(re.match(
        r'^(nil|nii|nls|nl|—|-|null|\.|n/a|bi|bs|by|ee|ca|we|cst|\s*)$',
        v.strip(), re.IGNORECASE))

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
    """Format datetime as '10 Jun 2026'."""
    return dt.strftime('%-d %b %Y') if hasattr(dt, 'strftime') else str(dt)

def parse(text, date):
    periods, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if re.match(r'^(Sub\s*Topic|Topic|CW|Words\s+for|Additional|GROUP)', line, re.IGNORECASE):
            continue
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
            continue
        m = re.match(r'^Submission\s*date?\s*(.*)', line, re.IGNORECASE)
        if m:
            val = clean(m.group(1))
            if val and not is_nil(val): cur['submission'] = val
            continue
    if cur and cur.get('subject'): periods.append(cur)
    return periods

def is_text_pdf(path):
    try:
        with pdfplumber.open(path) as pdf:
            text = ''.join(p.extract_text() or '' for p in pdf.pages)
            return len(text.strip()) > 100, text
    except Exception:
        return False, ''

def ocr_pdf(path):
    imgs = convert_from_path(path, dpi=400, poppler_path=POPPLER_PATH)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(
            ImageOps.autocontrast(img.convert('L')),
            config='--psm 4 --oem 1') + '\n'
    return text

def extract_date_from_filename(fname):
    m = re.search(r'(\d{2})[._](\d{2})[._](\d{2,4})', fname)
    if m:
        day, mon, yr = m.group(1), m.group(2), m.group(3)
        months = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                  '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
        mon_str = months.get(mon, mon)
        yr_short = yr[-2:] if len(yr) == 4 else yr
        return f"{day}-{mon_str}-{yr_short}"
    return None

def process_pdfs(pdf_paths):
    all_periods, dates_seen = [], []
    for path in pdf_paths:
        fname = os.path.basename(path)
        date_hint = extract_date_from_filename(fname)
        if date_hint: dates_seen.append(date_hint)
        is_text, text = is_text_pdf(path)
        if not is_text: text = ocr_pdf(path)
        all_periods += parse(text, date_hint or 'Unknown')

    # Week date calculations
    monday_dt = friday_dt = nxt_monday_dt = None
    if dates_seen:
        d = parse_date_str(dates_seen[0])
        if d:
            monday_dt     = d - timedelta(days=d.weekday())
            friday_dt     = monday_dt + timedelta(days=4)
            nxt_monday_dt = monday_dt + timedelta(days=7)

    rows = consolidate(
        all_periods,
        fmt(friday_dt)     if friday_dt     else 'Unknown',
        fmt(nxt_monday_dt) if nxt_monday_dt else 'Unknown'
    )
    return rows, fmt(monday_dt) if monday_dt else 'Unknown'

def consolidate(all_periods, friday_str, nxt_monday_str):
    subj_date = defaultdict(lambda: defaultdict(list))
    subj_sub  = defaultdict(lambda: 'NIL')
    seen = set()

    for p in all_periods:
        subj  = p.get('subject', '').strip()
        if not subj or subj.lower() in SKIP or len(subj) < 2: continue
        reinf = p.get('reinforcement', 'NIL')
        sub   = p.get('submission', 'NIL')
        date  = p.get('date', '')

        if not is_nil(reinf):
            key = (subj, reinf, date)
            if key not in seen:
                seen.add(key)
                subj_date[subj][date].append(reinf)

        if not is_nil(sub) and subj_sub[subj] == 'NIL':
            subj_sub[subj] = sub

    rows = []
    for subj in sorted(subj_date):
        dates = sorted(subj_date[subj])

        # Reinforcement dates formatted as "10 Jun 2026, 11 Jun 2026"
        reinf_dates = []
        for raw_date in dates:
            d = parse_date_str(raw_date)
            reinf_dates.append(fmt(d) if d else raw_date)

        # Consolidated reinforcement — one entry per date
        reinf_lines = []
        for raw_date in dates:
            hw = ', '.join(subj_date[subj][raw_date])
            reinf_lines.append(hw)

        # Submission date
        if subj == 'Math':
            submission = friday_str
        else:
            extracted = subj_sub[subj]
            if extracted != 'NIL':
                d = parse_date_str(extracted)
                submission = fmt(d) if d else extracted
            else:
                submission = nxt_monday_str

        rows.append({
            'subject':       subj,
            'reinf_dates':   reinf_dates,   # list of formatted date strings
            'reinf_lines':   reinf_lines,   # list of hw strings, parallel to reinf_dates
            'submission':    submission,
            'has_hw':        True
        })
    return rows

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': 'Please upload at least one PDF'}), 400
    saved = []
    try:
        for f in files:
            if f and f.filename.lower().endswith('.pdf'):
                path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
                f.save(path)
                saved.append(path)
        if not saved:
            return jsonify({'error': 'No valid PDFs found'}), 400
        rows, week_monday = process_pdfs(saved)
        return jsonify({'success': True, 'rows': rows,
                        'week': week_monday, 'files_processed': len(saved)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    print("🚀  Diary app → http://127.0.0.1:5000")
    app.run(debug=True, port=5000, host='0.0.0.0')