import os
import nltk
from flask import Flask, render_template, request, jsonify
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from collections import Counter
import random
import re

# Download required NLTK data
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

# Call this at startup
ensure_nltk_data()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def extract_text_from_file(file_path):
    """ফাইল থেকে টেক্সট বের করা"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def summarize_text(text, num_sentences=5):
    """টেক্সট সামারাইজ করা - সবচেয়ে গুরুত্বপূর্ণ বাক্য বের করা"""
    
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
    """টেক্সট থেকে মূল শব্দ বের করা"""
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text.lower())
    words = [word for word in words if word.isalnum() and word not in stop_words and len(word) > 3]
    
    word_freq = Counter(words)
    return [word for word, freq in word_freq.most_common(num_keywords)]

def generate_quiz(text, num_questions=5):
    """টেক্সট থেকে MCQ তৈরি করা"""
    sentences = sent_tokenize(text)
    keywords = extract_keywords(text, num_keywords=20)
    
    quiz = []
    used_sentences = set()
    
    for i in range(min(num_questions, len(sentences))):
        suitable_sentences = [s for s in sentences if s not in used_sentences and any(kw in s.lower() for kw in keywords)]
        
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

@app.route('/')
def index():
    """হোম পেজ"""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_file():
    """ফাইল প্রসেস করা"""
    file_path = None 
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'কোনো ফাইল পাওয়া যায়নি'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'ফাইল সিলেক্ট করুন'}), 400
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        text = extract_text_from_file(file_path)
        
        if len(text) < 100:
            return jsonify({'error': 'টেক্সট খুব ছোট। আরো বড় ফাইল দিন। (ন্যূনতম ১০০ অক্ষর)'}), 400
        
        num_sentences = int(request.form.get('summary_length', 5))
        summary = summarize_text(text, num_sentences)
        
        num_questions = int(request.form.get('quiz_questions', 5))
        quiz = generate_quiz(text, num_questions)
        
        keywords = extract_keywords(text, num_keywords=10)
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({
            'success': True,
            'summary': summary,
            'quiz': quiz,
            'keywords': keywords,
            'original_length': len(text),
            'summary_length': len(summary)
        })
    
    except Exception as e:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'একটি সমস্যা হয়েছে: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)