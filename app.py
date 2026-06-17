import os, re
from flask import Flask, request, jsonify, render_template
from pdf2image import convert_from_path
from PIL import ImageOps
import pytesseract
import pdfplumber
from collections import defaultdict
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')

# --- Path Config: Linux-friendly ---
# On Windows, you can keep the explicit paths if needed, 
# but for Render/Linux, we let the system find them via PATH
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# ... (Keep all your existing helper functions: norm_subj, is_nil, clean, parse, etc. here) ...

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    saved = []
    try:
        for f in files:
            if f and f.filename.lower().endswith('.pdf'):
                path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
                f.save(path)
                saved.append(path)
        
        rows, week_monday = process_pdfs(saved)
        return jsonify({'success': True, 'rows': rows, 'week': week_monday})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=5000)