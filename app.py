from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)
app.secret_key = 'kurly_nextmile_ds_secret_key'

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'instance', 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 🇰🇷 한국 시간(KST) 구하는 함수
def get_kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)

TEAM_USERS = {
    "NM9222": "관리자",
    "NM0085": "이상훈",
    "NM0141": "전민석",
    "NM0962": "한솔",
    "NM0805": "조인규",
    "NM0845": "주재영",
    "NM0989": "조재훈"
}

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start = db.Column(db.String(50), nullable=False)
    end = db.Column(db.String(50), nullable=True)

class Suggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), default="익명")
    created_at = db.Column(db.DateTime, default=get_kst_now)
    comments = db.relationship('Comment', backref='suggestion', cascade='all, delete-orphan', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    suggestion_id = db.Column(db.Integer, db.ForeignKey('suggestion.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), default="관리자")
    created_at = db.Column(db.DateTime, default=get_kst_now)

with app.app_context():
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    try:
        db.create_all()
    except Exception as e:
        print("DB init error:", e)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        if code in TEAM_USERS:
            session['user_code'] = code
            session['user_name'] = TEAM_USERS[code]
            session['is_admin'] = (code == "NM9222")
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="올바르지 않은 사번 코드입니다.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_code' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_name=session.get('user_name'))

@app.route('/suggestions')
def suggestions():
    if 'user_code' not in session:
        return redirect(url_for('login'))
    return render_template('suggestions.html', 
                           user_name=session.get('user_name'),
                           is_admin=session.get('is_admin', False))

# --- API ---
@app.route('/api/events', methods=['GET'])
def get_events():
    if 'user_code' not in session:
        return jsonify([]), 401
    try:
        events = Event.query.all()
        return jsonify([{'id': e.id, 'title': e.title, 'start': e.start, 'end': e.end} for e in events])
    except:
        return jsonify([])

@app.route('/api/events', methods=['POST'])
def add_event():
    if 'user_code' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    data = request.json
    new_event = Event(title=data['title'], start=data['start'], end=data.get('end'))
    db.session.add(new_event)
    db.session.commit()
    return jsonify({'status': 'success', 'id': new_event.id})

@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def delete_event(event_id):
    if 'user_code' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    event = Event.query.get(event_id)
    if event:
        db.session.delete(event)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404

# --- 건의함 API ---
@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    if 'user_code' not in session:
        return jsonify([]), 401
    try:
        sugs = Suggestion.query.order_by(Suggestion.id.desc()).all()
        result = []
        for s in sugs:
            comments_list = []
            for c in s.comments:
                comments_list.append({
                    'id': c.id,
                    'content': c.content,
                    'author': c.author,
                    'created_at': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else ''
                })
            result.append({
                'id': s.id,
                'title': s.title,
                'content': s.content,
                'author': s.author,
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '',
                'comments': comments_list
            })
        return jsonify(result)
    except Exception as e:
        print("Fetch error:", e)
        return jsonify([])

@app.route('/api/suggestions', methods=['POST'])
def add_suggestion():
    if 'user_code' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    try:
        data = request.json or {}
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        
        if not title or not content:
            return jsonify({'status': 'error', 'message': 'Empty fields'}), 400

        author_name = session.get('user_name', '익명')
        new_sug = Suggestion(title=title, content=content, author=author_name, created_at=get_kst_now())
        db.session.add(new_sug)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        print("Add suggestion error:", e)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/suggestions/<int:sug_id>', methods=['DELETE'])
def delete_suggestion(sug_id):
    if 'user_code' not in session or not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    sug = Suggestion.query.get(sug_id)
    if sug:
        db.session.delete(sug)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404

@app.route('/api/suggestions/<int:sug_id>/comments', methods=['POST'])
def add_comment(sug_id):
    if 'user_code' not in session or not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    try:
        data = request.json or {}
        content = data.get('content', '').strip()
        if not content:
            return jsonify({'status': 'error'}), 400

        comment = Comment(
            suggestion_id=sug_id, 
            content=content, 
            author=session.get('user_name', '관리자'),
            created_at=get_kst_now()
        )
        db.session.add(comment)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'user_code' not in session or not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403
    comment = Comment.query.get(comment_id)
    if comment:
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 404

if __name__ == '__main__':
    app.run(debug=True)