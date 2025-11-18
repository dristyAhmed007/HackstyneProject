import os
import nltk
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from collections import Counter
import random
import re
import sqlite3
import json
from datetime import datetime
import traceback

def ensure_nltk_data():
    """Ensure all required NLTK data is downloaded"""
    required_data = [
        ('tokenizers/punkt', 'punkt'),
        ('tokenizers/punkt_tab', 'punkt_tab'),
        ('corpora/stopwords', 'stopwords')
    ]
    for path, name in required_data:
        try:
            nltk.data.find(path)
        except LookupError:
            print(f"Downloading {name}...")
            nltk.download(name, quiet=True)

ensure_nltk_data()

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-12345'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

def init_db():
    """Initialize database with required tables"""
    try:
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      email TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Summaries table
        c.execute('''CREATE TABLE IF NOT EXISTS summaries
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      title TEXT NOT NULL,
                      summary TEXT NOT NULL,
                      keywords TEXT NOT NULL,
                      original_length INTEGER,
                      summary_length INTEGER,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users(id))''')
        
        # Quiz results table
        c.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      summary_id INTEGER,
                      score INTEGER NOT NULL,
                      total_questions INTEGER NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users(id),
                      FOREIGN KEY (summary_id) REFERENCES summaries(id))''')
        
        conn.commit()
        conn.close()
        print("✓ Database initialized successfully!")
    except Exception as e:
        print(f"✗ Database initialization error: {e}")

init_db()

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error', 'details': str(error)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Page not found'}), 404

@app.route('/')
def index():
    """Redirect to login if not authenticated, otherwise go to dashboard"""
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error in index: {e}")
        return str(e), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    try:
        if request.method == 'GET':
            if 'user_id' in session:
                return redirect(url_for('dashboard'))
            return render_template('login.html')
        
        # Handle POST request (login attempt)
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return jsonify({'success': True, 'message': 'Login successful!'})
        
        return jsonify({'error': 'Invalid username or password'}), 401
    
    except Exception as e:
        print(f"Login error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Login error: {str(e)}'}), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page and user creation"""
    try:
        if request.method == 'GET':
            return render_template('registration.html')
        
        data = request.json
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if not email or '@' not in email:
            return jsonify({'error': 'Valid email is required'}), 400
        
        hashed_password = generate_password_hash(password)
        
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                  (username, email, hashed_password))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Registration successful! Please login.'})
    
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 400
    except Exception as e:
        print(f"Registration error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Registration error: {str(e)}'}), 500

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Main dashboard page"""
    try:
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        return render_template('dashboard.html')
    
    except Exception as e:
        print(f"Dashboard error: {e}")
        print(traceback.format_exc())
        return f"Dashboard error: {str(e)}", 500

def extract_text_from_file(file_path):
    """Extract text from file"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def summarize_text(text, num_sentences=5):
    """Summarize text"""
    sentences = sent_tokenize(text)
    if len(sentences) <= num_sentences:
        return text
    
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text.lower())
    words = [word for word in words if word.isalnum() and word not in stop_words]
    word_freq = Counter(words)
    
    sentence_scores = {}
    for sentence in sentences:
        sentence_words = word_tokenize(sentence.lower())
        score = sum(word_freq.get(word, 0) for word in sentence_words if word.isalnum())
        sentence_scores[sentence] = score
    
    top_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
    
    summary = []
    for sentence in sentences:
        if sentence in top_sentences:
            summary.append(sentence)
    
    return ' '.join(summary)

def extract_keywords(text, num_keywords=10):
    """Extract keywords from text"""
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text.lower())
    words = [word for word in words if word.isalnum() and word not in stop_words and len(word) > 3]
    word_freq = Counter(words)
    return [word for word, freq in word_freq.most_common(num_keywords)]

def generate_quiz(text, num_questions=5):
    """Generate MCQ quiz from text"""
    sentences = sent_tokenize(text)
    keywords = extract_keywords(text, num_keywords=20)
    
    quiz = []
    used_sentences = set()
    
    for i in range(min(num_questions, len(sentences))):
        suitable_sentences = [s for s in sentences 
                            if s not in used_sentences 
                            and any(kw in s.lower() for kw in keywords)]
        
        if not suitable_sentences:
            break
        
        sentence = random.choice(suitable_sentences)
        used_sentences.add(sentence)
        
        sentence_words = word_tokenize(sentence.lower())
        important_words = [w for w in sentence_words if w in keywords and len(w) > 4]
        
        if not important_words:
            continue
        
        correct_answer = random.choice(important_words)
        question_text = re.sub(r'\b' + correct_answer + r'\b', '__', sentence, flags=re.IGNORECASE)
        
        wrong_options = [w for w in keywords if w != correct_answer]
        random.shuffle(wrong_options)
        wrong_options = list(set(wrong_options))[:3]
        
        all_options = wrong_options + [correct_answer]
        random.shuffle(all_options)
        
        quiz.append({
            'question': question_text,
            'options': all_options,
            'correct_answer': correct_answer
        })
    
    return quiz

@app.route('/process', methods=['POST'])
def process_file():
    """Process uploaded file"""
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first', 'redirect': '/login'}), 401
    
    file_path = None
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Please select a file'}), 400
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        text = extract_text_from_file(file_path)
        
        if len(text) < 100:
            return jsonify({'error': 'Text is too short. Please upload a larger file (minimum 100 characters)'}), 400
        
        num_sentences = int(request.form.get('summary_length', 5))
        summary = summarize_text(text, num_sentences)
        
        num_questions = int(request.form.get('quiz_questions', 5))
        quiz = generate_quiz(text, num_questions)
        
        keywords = extract_keywords(text, num_keywords=10)
        
        # Save to database
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        c.execute('''INSERT INTO summaries 
                     (user_id, title, summary, keywords, original_length, summary_length)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (session['user_id'], file.filename, summary, 
                   json.dumps(keywords), len(text), len(summary)))
        summary_id = c.lastrowid
        conn.commit()
        conn.close()
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({
            'success': True,
            'summary_id': summary_id,
            'summary': summary,
            'quiz': quiz,
            'keywords': keywords,
            'original_length': len(text),
            'summary_length': len(summary)
        })
        
    except Exception as e:
        print(f"Process error: {e}")
        print(traceback.format_exc())
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/my-summaries')
def my_summaries():
    """Get user's saved summaries"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        conn = sqlite3.connect('study_helper.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''SELECT id, title, summary, keywords, created_at 
                     FROM summaries WHERE user_id = ? 
                     ORDER BY created_at DESC''', (session['user_id'],))
        summaries = [dict(row) for row in c.fetchall()]
        conn.close()
        
        for s in summaries:
            s['keywords'] = json.loads(s['keywords'])
        
        return jsonify({'summaries': summaries})
    except Exception as e:
        print(f"My summaries error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/my-results')
def my_results():
    """Get user's quiz results"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        conn = sqlite3.connect('study_helper.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''SELECT score, total_questions, created_at 
                     FROM quiz_results WHERE user_id = ? 
                     ORDER BY created_at DESC''', (session['user_id'],))
        results = [dict(row) for row in c.fetchall()]
        conn.close()
        
        for r in results:
            r['total'] = r['total_questions']
            r['percentage'] = round((r['score'] / r['total_questions']) * 100) if r['total_questions'] > 0 else 0
        
        return jsonify({'results': results})
    except Exception as e:
        print(f"My results error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/save-quiz-result', methods=['POST'])
def save_quiz_result():
    """Save quiz result to database"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        data = request.json
        
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        c.execute('''INSERT INTO quiz_results 
                     (user_id, summary_id, score, total_questions)
                     VALUES (?, ?, ?, ?)''',
                  (session['user_id'], data.get('summary_id'), 
                   data['score'], data['total_questions']))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Save quiz result error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/delete-summary/<int:summary_id>', methods=['DELETE'])
def delete_summary(summary_id):
    """Delete a summary"""
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        
        conn = sqlite3.connect('study_helper.db')
        c = conn.cursor()
        c.execute('DELETE FROM summaries WHERE id = ? AND user_id = ?',
                  (summary_id, session['user_id']))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Delete summary error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("="*50)
    print("Study Helper App Starting...")
    print("="*50)
    print("Server running on http://127.0.0.1:5000")
    print("="*50)
    app.run(debug=True, port=5000, host='127.0.0.1')