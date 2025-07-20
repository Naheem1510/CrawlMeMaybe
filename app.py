from flask import Flask, render_template, request, send_file, jsonify
from flask_cors import CORS
import os
import csv
import json
import re
from datetime import datetime
from werkzeug.utils import secure_filename
from collections import Counter
import psycopg2
from psycopg2.extras import RealDictCursor
import PyPDF2
import docx2txt
from scraper import run_scraper
import psycopg2

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://neondb_owner:npg_8cZUEAjReq7r@ep-dark-dew-a12j94ng-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

app = Flask(__name__, template_folder='job-platform')
app.secret_key = 'job_matching_platform_2025_secret_key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'Uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
CORS(app, origins=["*"])
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

# Database connection
def get_db_connection():
    return psycopg2.connect(
        dbname="job_aggregator",
        user="postgres",
        password="5421",
        host="localhost",
        port="5432"
    )

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    try:
        jobs = run_scraper()  # Get jobs from scraper
        conn = get_db_connection()
        cur = conn.cursor()
        for job in jobs:
            cur.execute("""
                INSERT INTO jobs (title, company, location, salary, link, description, posted_date, source, sector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (link) DO NOTHING
            """, (
                job['title'], job['company'], job['location'], job['salary'],
                job['link'], job['description'], job['posted_date'],
                job['source'], job['sector']
            ))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': f'Added {len(jobs)} jobs to database'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/stats')
def api_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) AS total FROM jobs")
        total_jobs = cur.fetchone()['total']
        cur.execute("SELECT sector, COUNT(*) AS count FROM jobs GROUP BY sector")
        sectors = {row['sector']: row['count'] for row in cur.fetchall()}
        cur.execute("SELECT MAX(posted_date) AS latest FROM jobs")
        latest_update = cur.fetchone()['latest']
        cur.close()
        conn.close()
        return jsonify({
            'total_jobs': total_jobs,
            'sectors': sectors,
            'latest_update': latest_update.isoformat() if latest_update else None,
            'file_exists': True
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/jobs')
def api_jobs():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM jobs ORDER BY posted_date DESC LIMIT 20")
        jobs = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({'jobs': jobs, 'total': len(jobs)})
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/api/jobs/search')
def search_jobs():
    query = request.args.get('q', '').lower()
    sector = request.args.get('sector', '')
    location = request.args.get('location', '').lower()
    limit = int(request.args.get('limit', 50))
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM jobs WHERE 1=1"
        params = []
        if query:
            sql += " AND (LOWER(title) LIKE %s OR LOWER(description) LIKE %s)"
            params.extend([f'%{query}%', f'%{query}%'])
        if sector:
            sql += " AND sector = %s"
            params.append(sector)
        if location:
            sql += " AND LOWER(location) LIKE %s"
            params.append(f'%{location}%')
        sql += " LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        jobs = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({'jobs': jobs, 'total': len(jobs)})
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path):
    text = ""
    file_extension = file_path.rsplit('.', 1)[1].lower()
    try:
        if file_extension == 'pdf':
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() or ''
        elif file_extension == 'docx':
            text = docx2txt.process(file_path)
        elif file_extension == 'txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        elif file_extension == 'doc':
            with open(file_path, 'r', encoding='latin-1', errors='ignore') as file:
                text = file.read()
    except Exception as e:
        print(f"Error extracting text: {e}")
    return text

def analyze_cv_skills(cv_text):
    cv_text = cv_text.lower()
    skill_keywords = {
        'IT': ['python', 'java', 'javascript', 'react', 'node', 'sql', 'database', 'programming', 'software', 'web development', 'mobile app', 'cloud', 'aws', 'azure', 'devops', 'machine learning', 'ai', 'data science', 'cybersecurity', 'network', 'system admin', 'html', 'css', 'php', 'c++', 'c#', '.net', 'angular', 'vue', 'docker', 'kubernetes'],
        'Finance': ['accounting', 'finance', 'financial analysis', 'excel', 'sap', 'quickbooks', 'auditing', 'tax', 'banking', 'investment', 'budget', 'financial reporting', 'compliance', 'risk management', 'cpa', 'acca', 'cfa'],
        'Hospitality': ['hotel management', 'customer service', 'tourism', 'food service', 'restaurant', 'front desk', 'housekeeping', 'event planning', 'hospitality', 'guest relations', 'food and beverage', 'chef', 'cooking', 'culinary'],
        'Healthcare': ['nursing', 'medical', 'healthcare', 'patient care', 'clinical', 'pharmacy', 'laboratory', 'medical assistant', 'healthcare administration', 'medical records'],
        'Administration': ['administrative', 'office management', 'data entry', 'ms office', 'documentation', 'filing', 'scheduling', 'coordination', 'human resources', 'payroll'],
        'Retail': ['sales', 'customer service', 'retail', 'cashier', 'inventory', 'merchandising', 'point of sale', 'pos'],
        'Technical': ['technical', 'maintenance', 'repair', 'mechanical', 'electrical', 'engineering', 'technician', 'troubleshooting']
    }
    detected_skills = []
    sector_scores = {}
    for sector, skills in skill_keywords.items():
        score = 0
        sector_skills = []
        for skill in skills:
            if skill in cv_text:
                score += 1
                sector_skills.append(skill)
                detected_skills.append(skill)
        sector_scores[sector] = {'score': score, 'skills': sector_skills}
    return detected_skills, sector_scores

def match_jobs_to_cv(cv_skills, sector_scores):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM jobs")
        jobs = cur.fetchall()
        cur.close()
        conn.close()
        matches = []
        for job in jobs:
            job_title = job['title'].lower()
            job_description = job['description'].lower() if job['description'] else ''
            job_sector = job['sector'] or 'Other'
            match_score = 0
            matched_skills = []
            for skill in cv_skills:
                if skill in job_title or skill in job_description:
                    match_score += 2
                    matched_skills.append(skill)
            if job_sector in sector_scores and sector_scores[job_sector]['score'] > 0:
                match_score += sector_scores[job_sector]['score']
            if match_score > 0:
                matches.append({
                    'job': job,
                    'match_score': match_score,
                    'matched_skills': matched_skills,
                    'match_percentage': min(match_score * 10, 100)
                })
        matches.sort(key=lambda x: x['match_score'], reverse=True)
        return matches[:20]
    except Exception as e:
        print(f"Error matching jobs: {e}")
        return []

@app.route('/api/upload-cv', methods=['POST'])
def upload_cv():
    if 'cv_file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['cv_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        user_id = request.form.get('user_id', 'anonymous')
        try:
            file.save(file_path)
            cv_text = extract_text_from_file(file_path)
            if not cv_text.strip():
                os.remove(file_path)
                return jsonify({'error': 'Could not extract text from CV'}), 400
            detected_skills, sector_scores = analyze_cv_skills(cv_text)
            job_matches = match_jobs_to_cv(detected_skills, sector_scores)
            # Store CV data in database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cvs (user_id, filename, skills, sector_scores)
                VALUES (%s, %s, %s, %s)
            """, (user_id, filename, ','.join(detected_skills), json.dumps(sector_scores)))
            conn.commit()
            cur.close()
            conn.close()
            os.remove(file_path)
            return jsonify({
                'success': True,
                'detected_skills': detected_skills[:20],
                'sector_scores': sector_scores,
                'job_matches': job_matches,
                'total_matches': len(job_matches)
            })
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({'error': f'Error processing CV: {str(e)}'}), 500
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/visualization/data')
def get_visualization_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT sector, COUNT(*) AS count FROM jobs GROUP BY sector")
        sectors = {row['sector']: row['count'] for row in cur.fetchall()}
        cur.execute("SELECT location, COUNT(*) AS count FROM jobs GROUP BY location LIMIT 10")
        locations = {row['location']: row['count'] for row in cur.fetchall()}
        cur.execute("SELECT company, COUNT(*) AS count FROM jobs GROUP BY company ORDER BY count DESC LIMIT 10")
        top_companies = {row['company']: row['count'] for row in cur.fetchall()}
        cur.execute("SELECT DATE(posted_date) AS date, COUNT(*) AS count FROM jobs GROUP BY DATE(posted_date)")
        jobs_by_date = {row['date'].isoformat(): row['count'] for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) AS total FROM jobs")
        total_jobs = cur.fetchone()['total']
        cur.close()
        conn.close()
        return jsonify({
            'sectors': sectors,
            'locations': locations,
            'top_companies': top_companies,
            'jobs_by_date': jobs_by_date,
            'total_jobs': total_jobs
        })
    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/download')
def download():
    csv_path = "C:/Users/nahee/Downloads/fortomorrow/Web_Scrappingg/Web_Scrapping/jobs.csv"
    if os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True, download_name=f'jobs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
    return jsonify({'error': 'No jobs.csv file found!'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)