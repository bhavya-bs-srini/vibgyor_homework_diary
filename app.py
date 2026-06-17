import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import Image, ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# --- CONFIGURATION FOR WINDOWS/LINUX ---
IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    POPPLER_PATH = None 

# --- FUNCTIONS ---
# [Keep all your existing helper functions here: norm_subj, is_nil, clean, parse_date_str, fmt, parse, is_text_pdf, extract_date_from_filename, consolidate]

def ocr_pdf(path):
    kwargs = {'dpi': 400}
    if POPPLER_PATH:
        kwargs['poppler_path'] = POPPLER_PATH
    
    imgs = convert_from_path(path, **kwargs)
    text = ''
    for img in imgs:
        text += pytesseract.image_to_string(
            ImageOps.autocontrast(img.convert('L')),
            config='--psm 4 --oem 1') + '\n'
    return text

# --- ROUTES ---
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
        rows, week_monday = process_pdfs(saved)
        return jsonify({'success': True, 'rows': rows, 'week': week_monday})
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(debug=True, port=5000, host='0.0.0.0')