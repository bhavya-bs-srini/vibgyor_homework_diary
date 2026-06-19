import os, re, base64
from io import BytesIO
from flask import Flask, request, jsonify, render_template
from collections import defaultdict
from datetime import datetime, timedelta
import requests

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

POPPLER_PATH = os.environ.get('POPPLER_PATH', None)
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '')

SKIP = {
    'assembly', 'break', 'lunch', 'sports', 'pe', 'dance',
    'music', 'yoga', 'meditation', 'skill', 'unknown'
}

SUBJ_MAP = {
    'language arts(support)': 'Language Arts (Support)',
    'language arts': 'Language Arts',
    'literature': 'Literature',
    'ssc': 'SSC',
    'math': 'Math',
    'mathematics': 'Math',
    'art': 'Art',
    'computer': 'Computer',
    'robotics': 'Robotics',
    '2nd language -hindi': '2ND LANGUAGE - Hindi',
    '2nd ianguage -hindi': '2ND LANGUAGE - Hindi',
    '2nd language -kannada': '2ND LANGUAGE - Kannada',
    '2nd ianguage -kannada': '2ND LANGUAGE - Kannada',
    '3rd language -hindi': '3RD LANGUAGE - Hindi',
    '3rd language -kannada': '3RD LANGUAGE - Kannada',
}

def norm_subj(s):
    raw = s.strip()
    lower = raw.lower()
    for k in sorted(SUBJ_MAP, key=len, reverse=True):
        if k in lower:
            return SUBJ_MAP[k]
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
    # Try numeric: 18_06_26 or 18.06.2026
    m = re.search(r'(\d{1,2})[_.](\d{1,2})[_.](\d{2,4})', basename)
    if m:
        day, mon, yr = m.groups()
        return datetime(int('20'+yr if len(yr)==2 else yr), int(mon), int(day))
    # Try: 18-Jun-26 or 18-Jun-2026
    m2 = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{2,4})', basename)
    if m2:
        day, mon_str, yr = m2.groups()
        return datetime.strptime(f"{day}-{mon_str}-{'20'+yr if len(yr)==2 else yr}", "%d-%b-%Y")
    return datetime.today()

def fmt_dt(dt): return dt.strftime('%d %b %Y')
def monday_of(dt): return dt - timedelta(days=dt.weekday())
def friday_of(mon): return mon + timedelta(days=4)
def next_monday(mon): return mon + timedelta(days=7)

def pdf_to_base64(path):
    """Convert PDF to base64 string for Mistral API."""
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def mistral_ocr(path):
    """Send PDF directly to Mistral OCR API and return extracted text."""
    b64_pdf = pdf_to_base64(path)

    headers = {
        'Authorization': f'Bearer {MISTRAL_API_KEY}',
        'Content-Type': 'application/json'
    }

    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64_pdf}"
        }
    }

    resp = requests.post(
        'https://api.mistral.ai/v1/ocr',
        headers=headers,
        json=payload,
        timeout=60
    )
    resp.raise_for_status()
    result = resp.json()

    # Combine text from all pages
    full_text = ''
    for page in result.get('pages', []):
        full_text += page.get('markdown', '') + '\n'

    app.logger.info(f"Mistral OCR result:\n{full_text[:500]}")
    return full_text

def parse(text, pdf_date_dt):
    periods = []
    cur = None

    for line in text.splitlines():
        line = line.strip()
        # Strip markdown artifacts from Mistral output
        line = re.sub(r'[*#`|]+', '', line).strip()
        if not line:
            continue

        # Match "Period - 1", "Period-1", "Period : 1"
        if re.match(r'^Period\s*[-:]\s*\d+', line, re.IGNORECASE):
            if cur and cur.get('subject') and cur['subject'] != 'Unknown':
                periods.append(cur)
            cur = {
                'pdf_date': pdf_date_dt,
                'subject': 'Unknown',
                'reinforcement': 'NIL',
                'submission': None
            }
            continue

        if cur is None:
            continue

        lower = line.lower()

        # Subject
        if re.match(r'^subject\b', lower):
            val = re.split(r'^subject\s*[:\s]\s*', line, flags=re.IGNORECASE, maxsplit=1)
            if len(val) > 1 and val[1].strip():
                cur['subject'] = norm_subj(val[1])

        # Reinforcement
        elif re.match(r'^reinforcement\b', lower):
            val = re.split(r'^reinforcement\s*[:\s]\s*', line, flags=re.IGNORECASE, maxsplit=1)
            if len(val) > 1:
                r = clean_reinf(val[1])
                if not is_nil(r):
                    cur['reinforcement'] = r

        # Submission date
        elif re.match(r'^submission\s*date\b', lower):
            val = re.split(r'^submission\s*date\s*[:\s]\s*', line, flags=re.IGNORECASE, maxsplit=1)
            if len(val) > 1 and val[1].strip() and not is_nil(val[1]):
                cur['submission'] = val[1].strip()

    # Don't forget the last period
    if cur and cur.get('subject') and cur['subject'] != 'Unknown':
        periods.append(cur)

    return periods

def consolidate_by_week(all_periods):
    week_data = defaultdict(lambda: defaultdict(list))
    for p in all_periods:
        subj = p['subject']
        reinf = p['reinforcement']

        if is_nil(reinf) or subj.lower() in SKIP:
            continue

        mon = monday_of(p['pdf_date'])
        week_data[mon][subj].append({
            'reinf': reinf,
            'date': p['pdf_date'],
            'submission': p.get('submission')
        })

    output = []
    for mon in sorted(week_data.keys()):
        rows = []
        for subj, items in week_data[mon].items():
            submission = items[0].get('submission') or \
                fmt_dt(friday_of(mon) if 'math' in subj.lower() else next_monday(mon))
            rows.append({
                'subject': subj,
                'reinf_dates': [fmt_dt(i['date']) for i in items],
                'reinf_lines': [i['reinf'] for i in items],
                'submission': submission
            })
        output.append({
            'monday': fmt_dt(mon),
            'friday': fmt_dt(friday_of(mon)),
            'rows': rows
        })
    return output

@app.route('/health')
def health():
    import shutil
    return jsonify({
        'pdftoppm': shutil.which('pdftoppm'),
        'uploads_dir': os.path.exists(app.config['UPLOAD_FOLDER']),
        'mistral_api_key_set': bool(MISTRAL_API_KEY)
    })

@app.route('/process', methods=['POST'])
def process():
    saved = []
    try:
        if not MISTRAL_API_KEY:
            return jsonify({'error': 'Mistral API key not configured on server.'}), 500

        files = request.files.getlist('pdfs')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files uploaded.'}), 400

        all_periods = []
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)
            pdf_date = parse_date_from_filename(f.filename)
            text = mistral_ocr(path)
            all_periods.extend(parse(text, pdf_date))

        weeks = consolidate_by_week(all_periods)
        return jsonify({'weeks': weeks})

    except Exception as e:
        app.logger.exception("Error in /process")
        return jsonify({'error': str(e)}), 500

    finally:
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