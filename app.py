from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.secret_key = 'kurly_nextmile_ds_secret_key'

# SQLite DB 설정
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 🔑 7인 전용 로그인 코드 및 사용자 명단
TEAM_USERS = {
    "NM9222": "관리자",
    "NM0085": "이상훈",
    "NM0141": "전민석",
    "NM0962": "한솔",
    "NM0805": "조인규",
    "NM0845": "주재영",
    "NM0989": "조재훈"
}

# DB 모델
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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

# 데이터베이스 자동 생성
with app.app_context():
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    db.create_all()

# 🔑 로그인 페이지 (첫 접속 화면)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()  # 대소문자 구별 없이 입력 처리
        if code in TEAM_USERS:
            session['user_code'] = code
            session['user_name'] = TEAM_USERS[code]
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="올바르지 않은 사번 코드입니다.")
    return render_template('login.html')

# 🚪 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# 📅 메인 달력 페이지 (로그인 필수)
@app.route('/')
def index():
    if 'user_code' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_name=session.get('user_name'))

# 💡 건의함 페이지 (로그인 필수)
@app.route('/suggestions')
def suggestions():
    if 'user_code' not in session:
        return redirect(url_for('login'))
    return render_template('suggestions.html', user_name=session.get('user_name'))

# --- API ---
@app.route('/api/events', methods=['GET'])
def get_events():
    if 'user_code' not in session:
        return jsonify([]), 401
    events = Event.query.all()
    return jsonify([{'id': e.id, 'title': e.title, 'start': e.start, 'end': e.end} for e in events])

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

if __name__ == '__main__':
    app.run(debug=True)