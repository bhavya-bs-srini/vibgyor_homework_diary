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

# Linux-compatible path configuration (works on Render)
POPPLER_PATH = os.environ.get('POPPLER_PATH', None)  # None = auto-detect on Linux
TESSERACT_CMD = os.environ.get('TESSERACT_CMD', 'tesseract')  # Linux default path
if os.path.exists(TESSERACT_CMD) or TESSERACT_CMD != 'tesseract':
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Minimal SKIP list to avoid over-filtering
SKIP = {'assembly', 'break', 'lunch', 'sports', 'pe', 'dance', 'music', 'yoga', 'meditation'}

SUBJ_MAP = {
    'language arts': 'Language Arts', 'literature': 'Literature',
    'ssc': 'SSC', 'math': 'Math', 'mathematics': 'Math',
    'art': 'Art', 'computer': 'Computer', 'robotics': 'Robotics',
    '2nd language -hindi': '2ND LANGUAGE - Hindi',
    '2nd language -kannada': '2ND LANGUAGE - Kannada',
    '3rd language -hindi': '3RD LANGUAGE - Hindi',
    '3rd language -kannada': '3RD LANGUAGE - Kannada'
}

PAREN_CLEAN = re.compile(r'[\[\]_=\|\\,\(\)\-]+')

def norm_subj(s):
    raw = s.strip()
    lower = raw.lower()
    for k, v in SUBJ_MAP.items():
        if k in lower: return v
    return raw.title()

OCR_NOISE = re.compile(r'^(nil|nii|nls|nl|n|l|—|-|null|\.|\s*)$', re.IGNORECASE)

def is_nil(v):
    if not v: return True
    return bool(OCR_NOISE.match(v.strip()))

def clean_val(v):
    return re.sub(r'^[\[\|\\=_\-:\s]+|[\[\|\\=_\-~\s]+$', '', str(v)).strip()

def clean_reinf(v):
    v = clean_val(v)
    return re.sub(r'^[^A-Za-z0-9]+', '', v)

def parse_date_from_filename(basename):
    # Try numeric format: 18.06.2026 or 18_06_2026
    m = re.search(r'(\d{1,2})[_.](\d{1,2})[_.](\d{2,4})', basename)
    if m:
        day, mon, yr = m.groups()
        return datetime(int('20'+yr if len(yr)==2 else yr), int(mon), int(day))
    
    # Try format: 18-Jun-26 or 18-Jun-2026
    m2 = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', basename)
    if m2:
        day, mon_str, yr = m2.groups()
        return datetime.strptime(
            f"{day}-{mon_str}-{'20'+yr if len(yr)==2 else yr}",
            "%d-%b-%Y"
        )
    
    return datetime.today()

def fmt_dt(dt): return dt.strftime('%d %b %Y')
def monday_of(dt): return dt - timedelta(days=dt.weekday())
def friday_of(mon): return mon + timedelta(days=4)
def next_monday(mon): return mon + timedelta(days=7)

def pdf_to_text(path):
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + "\n"
    except Exception:
        # Fallback to OCR
        convert_kwargs = {'dpi': 300}
        if POPPLER_PATH:
            convert_kwargs['poppler_path'] = POPPLER_PATH
        imgs = convert_from_path(path, **convert_kwargs)
        for img in imgs:
            text += pytesseract.image_to_string(img) + "\n"
    return text

def parse(text, pdf_date_dt):
    periods = []
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^Period\s*[-:]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject'): periods.append(cur)
            cur = {'pdf_date': pdf_date_dt, 'subject': 'Unknown', 'reinforcement': 'NIL'}
        elif cur is not None:
            if 'subject' in line.lower() and ':' in line:
                cur['subject'] = norm_subj(line.split(':', 1)[1])
            elif 'reinforcement' in line.lower() and ':' in line:
                cur['reinforcement'] = clean_reinf(line.split(':', 1)[1])
    if cur and cur.get('subject'): periods.append(cur)
    return periods

def consolidate_by_week(all_periods):
    week_data = defaultdict(lambda: defaultdict(list))
    for p in all_periods:
        subj = p['subject']
        reinf = p['reinforcement']
        print(f"Processing: {subj} | Reinforcement: {reinf}")

        if is_nil(reinf) or subj.lower() in SKIP:
            continue

        mon = monday_of(p['pdf_date'])
        week_data[mon][subj].append({'reinf': reinf, 'date': p['pdf_date']})

    output = []
    for mon in sorted(week_data.keys()):
        rows = []
        for subj, items in week_data[mon].items():
            rows.append({
                'subject': subj,
                'reinf_dates': [fmt_dt(i['date']) for i in items],
                'reinf_lines': [i['reinf'] for i in items],
                'submission': fmt_dt(friday_of(mon) if 'math' in subj.lower() else next_monday(mon))
            })
        output.append({'monday': fmt_dt(mon), 'friday': fmt_dt(friday_of(mon)), 'rows': rows})
    return output

@app.route('/process', methods=['POST'])
def process():
    saved = []
    try:
        files = request.files.getlist('pdfs')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files uploaded.'}), 400

        all_periods = []
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)
            all_periods.extend(parse(pdf_to_text(path), parse_date_from_filename(f.filename)))

        weeks = consolidate_by_week(all_periods)
        return jsonify({'weeks': weeks})

    except Exception as e:
        app.logger.exception("Error in /process")
        return jsonify({'error': str(e)}), 500

    finally:
        # Always clean up uploaded files, even if an error occurred
        for p in saved:
            try:
                os.remove(p)
            except OSError:
                pass

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)