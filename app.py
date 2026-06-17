import os
from flask import Flask, render_template
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)

# --- Helper Functions ---

def get_monday(date_str):
    date_obj = datetime.strptime(date_str, "%d-%b-%y")
    return (date_obj - timedelta(days=date_obj.weekday())).strftime("%d-%b-%y")

def get_submission_date(subject, date_str):
    d = datetime.strptime(date_str, "%d-%b-%y")
    # Math: Friday of the same week
    if "math" in subject.lower():
        return (d + timedelta(days=(4 - d.weekday()))).strftime("%d-%b-%y")
    # Default: Next Monday
    return (d + timedelta(days=(7 - d.weekday()))).strftime("%d-%b-%y")

def extract_data_from_pdfs():
    """
    REPLACE THIS LOGIC with your actual OCR parsing.
    It must return a list of dictionaries.
    """
    # Example format:
    # return [{'subject': 'SSC', 'date': '10-Jun-26', 'reinforcement': '5A, 5B'}, ...]
    return [] 

# --- Routes ---

@app.route('/')
def index():
    # 1. Fetch live data
    extracted_items = extract_data_from_pdfs()
    
    # 2. Grouping logic
    grouped_data = defaultdict(lambda: defaultdict(list))
    
    for item in extracted_items:
        # Filter out "NIL" or empty reinforcement entries
        reinforcement = item.get('reinforcement', 'NIL')
        if reinforcement.upper() == 'NIL':
            continue
            
        week = get_monday(item['date'])
        sub = item['subject']
        
        grouped_data[week][sub].append({
            'date': item['date'],
            'reinforcement': reinforcement,
            'submission': get_submission_date(sub, item['date'])
        })
        
    # 3. Pass grouped_data to template
    return render_template('index.html', data=grouped_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)