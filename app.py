import os
from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)

def get_monday(date_str):
    date_obj = datetime.strptime(date_str, "%d-%b-%y")
    return (date_obj - timedelta(days=date_obj.weekday())).strftime("%d-%b-%y")

def get_submission_date(subject, date_str):
    d = datetime.strptime(date_str, "%d-%b-%y")
    if "math" in subject.lower():
        # Friday of current week
        return (d + timedelta(days=(4 - d.weekday()))).strftime("%d-%b-%y")
    # Default: Next Monday
    return (d + timedelta(days=(7 - d.weekday()))).strftime("%d-%b-%y")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    # Assume 'extracted_data' comes from your OCR parsing logic
    # Structure: [{'subject': 'Math', 'date': '10-Jun-26', 'reinforcement': '6'}, ...]
    extracted_data = [...] 
    
    # Nested grouping: {week_monday: {subject: [tasks]}}
    grouped_data = defaultdict(lambda: defaultdict(list))
    
    for item in extracted_data:
        week = get_monday(item['date'])
        sub = item['subject']
        grouped_data[week][sub].append({
            'date': item['date'],
            'reinforcement': item['reinforcement'],
            'submission': get_submission_date(sub, item['date'])
        })
        
    return jsonify(grouped_data)