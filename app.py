import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# ── Subjects to skip ─────────────────────────────────────────────────────────
SKIP = {
    'assembly', 'spark', 'library', 'skill', 'enrichment',
    'language arts(support)', 'literature(support)',
    'math-support', 'math support', 'public speaking'
}

# ── Canonical subject names ──────────────────────────────────────────────────
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
    '3rd language-hindi':    '3RD LANGUAGE - Hindi',
    '3rd language -hindi':   '3RD LANGUAGE - Hindi',
    '3rdlanguage-hindi':     '3RD LANGUAGE - Hindi',
    '3rd language - hindi':  '3RD LANGUAGE - Hindi',
    'srdlanguage-hindi':     '3RD LANGUAGE - Hindi',
    '3rd language-kannada':  '3RD LANGUAGE - Kannada',
    '3rdlanguage-kannada':   '3RD LANGUAGE - Kannada',
    '3rd language - kannada':'3RD LANGUAGE - Kannada',
    'srdlanguagekannada':    '3RD LANGUAGE - Kannada',
}

def norm_subj(s):
    s = re.sub(r'[\[\]_=\|\\,\(\)]+', ' ', s.strip().lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return SUBJ_MAP.get(s, s.title())

def is_nil(v):
    return bool(re.match(
        r'^(nil|nii|nls|nl|—|-|null|\.|n/a|bi|bs|by|ee|ca|we|cst|\s*)$',
        str(v).strip(), re.IGNORECASE
    ))

def clean(v):
    v = re.sub(r'^[\[\|\\=_\-:\s]+', '', str(v))
    v = re.sub(r'[\[\|\\=_\-—~\s]+$', '', v)
    return v.strip()

# ── Date helpers ─────────────────────────────────────────────────────────────

def parse_date_from_filename(basename):
    """
    Handles filenames like: Daily_Diary_Communication_3A_10_06_26.pdf
    Extracts the last three numeric groups as DD, MM, YY/YYYY.
    """
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

# ── OCR ──────────────────────────────────────────────────────────────────────

def ocr_pdf(path):
    imgs = convert_from_path(path, dpi=200)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(
            ImageOps.autocontrast(img.convert('L')),
            config='--psm 4 --oem 1'
        ) + '\n'
    return text

# ── Parse one PDF's OCR text ─────────────────────────────────────────────────

def parse(text, pdf_date_dt):
    """
    Returns list of dicts: { pdf_date, subject, reinforcement }
    Submission date is intentionally NOT read from the PDF.
    """
    periods = []
    cur = None
    pending_header = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r'^(Sub\s*Topic|Topic|CW|Words\s+for|Additional|GROUP)', line, re.IGNORECASE):
            continue

        if re.match(r'^Period\s*[-–]\s*\d+', line, re.IGNORECASE):
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
            val = clean(m_subj.group(1))
            if val: cur['subject'] = norm_subj(val)
            else:   pending_header = 'subject'
            continue

        if m_reinf:
            val = clean(m_reinf.group(1))
            if val: cur['reinforcement'] = val
            else:   pending_header = 'reinforcement'
            continue

        if pending_header:
            val = clean(line)
            if not is_nil(val):
                if pending_header == 'subject':       cur['subject'] = norm_subj(val)
                elif pending_header == 'reinforcement': cur['reinforcement'] = val
            pending_header = None

    if cur and cur.get('subject'):
        periods.append(cur)
    return periods

# ── Consolidate periods into rows, grouped by week ───────────────────────────

def consolidate_by_week(all_periods):
    """
    Groups periods by the ISO Monday of their pdf_date.
    Returns a list of week-blocks, each:
      {
        'monday':  '9 Jun 2026',
        'friday':  '13 Jun 2026',
        'rows': [
          { subject, reinf_dates: [...], reinf_lines: [...], submission }
        ]
      }
    sorted oldest week first.
    """
    # week_key (monday datetime) → subj → date_str → [reinf, ...]
    week_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    seen = set()

    for p in all_periods:
        subj = p.get('subject', '').strip()
        if not subj or subj.lower() in SKIP or len(subj) < 2:
            continue
        if is_nil(p.get('reinforcement')):
            continue

        pdf_dt   = p['pdf_date']
        mon_dt   = monday_of(pdf_dt)
        date_key = fmt_dt(pdf_dt)
        reinf    = p['reinforcement']

        dedup = (mon_dt, subj, reinf, date_key)
        if dedup in seen:
            continue
        seen.add(dedup)
        week_data[mon_dt][subj][date_key].append(reinf)

    def sort_date_key(ds):
        for fmt in ('%-d %b %Y', '%d %b %Y'):
            try: return datetime.strptime(ds, fmt)
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

# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(path)
            saved.append(path)

        all_periods = []
        for path in saved:
            pdf_date_dt = parse_date_from_filename(os.path.basename(path)) or datetime.today()
            text = ocr_pdf(path)
            all_periods += parse(text, pdf_date_dt)

        weeks = consolidate_by_week(all_periods)
        return jsonify({'success': True, 'weeks': weeks, 'files_processed': len(saved)})

    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
