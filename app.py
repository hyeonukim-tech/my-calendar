from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)
app.secret_key = 'kurly_nextmile_ds_secret_key'

# ----------------------------------------------------
# 🛡️ Supabase 외부 DB 우선 연결 (없을 경우 로컬 SQLite 사용)
# ----------------------------------------------------
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir, 'instance')
db_path = os.path.join(instance_dir, 'app.db')

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or ('sqlite:///' + db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

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

# 1. 달력 일정
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start = db.Column(db.String(50), nullable=False)
    end = db.Column(db.String(50), nullable=True)

# 2. 익명 건의함
class Suggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), default="익명")
    created_at = db.Column(db.DateTime, default=get_kst_now)
    comments = db.relationship('Comment', backref='suggestion', cascade='all, delete-orphan', lazy=True)

# 3. 건의함 댓글
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    suggestion_id = db.Column(db.Integer, db.ForeignKey('suggestion.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), default="관리자")
    created_at = db.Column(db.DateTime, default=get_kst_now)

# 4. 실시간 접속자
class UserStatus(db.Model):
    user_code = db.Column(db.String(20), primary_key=True)
    user_name = db.Column(db.String(50), nullable=False)
    last_active = db.Column(db.DateTime, default=get_kst_now)

# 🛡️ 안전한 테이블 및 컬럼 자동 보완 (Auto Migration)
with app.app_context():
    os.makedirs(instance_dir, exist_ok=True)
    db.create_all()
    
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'suggestion' in tables:
            columns = [c['name'] for c in inspector.get_columns('suggestion')]
            with db.engine.connect() as conn:
                if 'author' not in columns:
                    conn.execute(text("ALTER TABLE suggestion ADD COLUMN author VARCHAR(50) DEFAULT '익명';"))
                if 'created_at' not in columns:
                    conn.execute(text("ALTER TABLE suggestion ADD COLUMN created_at DATETIME;"))
                conn.commit()
                
        if 'comment' in tables:
            columns = [c['name'] for c in inspector.get_columns('comment')]
            with db.engine.connect() as conn:
                if 'author' not in columns:
                    conn.execute(text("ALTER TABLE comment ADD COLUMN author VARCHAR(50) DEFAULT '관리자';"))
                if 'created_at' not in columns:
                    conn.execute(text("ALTER TABLE comment ADD COLUMN created_at DATETIME;"))
                conn.commit()
    except Exception as e:
        print("Safety Migration Check:", e)

@app.before_request
def update_last_active():
    if 'user_code' in session:
        code = session['user_code']
        name = session.get('user_name', '사용자')
        try:
            status = UserStatus.query.get(code)
            if not status:
                status = UserStatus(user_code=code, user_name=name, last_active=get_kst_now())
                db.session.add(status)
            else:
                status.last_active = get_kst_now()
            db.session.commit()
        except:
            db.session.rollback()

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
    if 'user_code' in session:
        try:
            status = UserStatus.query.get(session['user_code'])
            if status:
                db.session.delete(status)
                db.session.commit()
        except:
            pass
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

@app.route('/api/online_users', methods=['GET'])
def get_online_users():
    if 'user_code' not in session:
        return jsonify([]), 401
    try:
        five_mins_ago = get_kst_now() - timedelta(minutes=5)
        online_statuses = UserStatus.query.filter(UserStatus.last_active >= five_mins_ago).all()
        online_names = [u.user_name for u in online_statuses]
        return jsonify(online_names)
    except:
        return jsonify([])

# --- 달력 API ---
@app.route('/api/events', methods=['GET'])
def get_events():
    if 'user_code' not in session:
        return jsonify([]), 401
    try:
        events = Event.query.all()
        return jsonify([{'id': e.id, 'title': e.title, 'start': e.start, 'end': e.end} for e in events])
    except Exception as e:
        print("Fetch events error:", e)
        return jsonify([])

@app.route('/api/events', methods=['POST'])
def add_event():
    if 'user_code' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    try:
        data = request.get_json(silent=True) or {}
        new_event = Event(title=data.get('title',''), start=data.get('start',''), end=data.get('end'))
        db.session.add(new_event)
        db.session.commit()
        return jsonify({'status': 'success', 'id': new_event.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
            if hasattr(s, 'comments') and s.comments:
                for c in s.comments:
                    comments_list.append({
                        'id': c.id,
                        'content': c.content,
                        'author': getattr(c, 'author', '관리자'),
                        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M') if getattr(c, 'created_at', None) else ''
                    })
            result.append({
                'id': s.id,
                'title': s.title,
                'content': s.content,
                'author': getattr(s, 'author', '익명'),
                'created_at': s.created_at.strftime('%Y-%m-%d %H:%M') if getattr(s, 'created_at', None) else '',
                'comments': comments_list
            })
        return jsonify(result)
    except Exception as e:
        print("Fetch error:", e)
        return jsonify([])

@app.route('/api/suggestions', methods=['POST'])
def add_suggestion():
    if 'user_code' not in session:
        return jsonify({'status': 'unauthorized', 'message': '로그인이 필요합니다.'}), 401
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        
        if not title or not content:
            return jsonify({'status': 'error', 'message': '제목과 내용을 모두 입력해 주세요.'}), 400

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
        data = request.get_json(silent=True) or {}
        content = data.get('content', '').strip()
        if not content:
            return jsonify({'status': 'error', 'message': '내용을 입력하세요.'}), 400

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