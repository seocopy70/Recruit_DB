import os
from datetime import datetime, timezone
from contextlib import contextmanager
from datetime import date
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from dotenv import load_dotenv
from backup import run_backup

# 환경 변수 로드
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

# PostgreSQL 연결 풀 초기화 (Oracle VM의 recruit_db)
# 예: DATABASE_URL=postgresql://USER:PASSWORD@10.0.0.50:5432/recruit_db
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL 환경변수가 설정되지 않았습니다.')

pool = ThreadedConnectionPool(1, 5, DATABASE_URL, connect_timeout=10)


@contextmanager
def get_cursor():
    """풀에서 연결을 받아 커서를 제공하고, 성공 시 commit / 실패 시 rollback 합니다."""
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def serialize(row):
    """datetime/date 값을 프론트가 기대하는 문자열(ISO)로 변환합니다."""
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


# PWA 리소스는 웹 루트에서 제공해야 Service Worker가 사이트 전체를 제어할 수 있습니다.
@app.route('/manifest.webmanifest')
def pwa_manifest():
    return send_from_directory(app.static_folder, 'manifest.webmanifest', mimetype='application/manifest+json')

@app.route('/sw.js')
def pwa_service_worker():
    response = make_response(send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.after_request
def add_pwa_metadata(response):
    # HTML head에 PWA 메타데이터를 주입해 기존 템플릿 기능은 그대로 유지합니다.
    if request.path == '/' and response.content_type.startswith('text/html'):
        html = response.get_data(as_text=True)
        marker = '</head>'
        if marker in html and 'manifest.webmanifest' not in html:
            pwa_head = '''\n    <meta name="theme-color" content="#0d6efd">\n    <meta name="mobile-web-app-capable" content="yes">\n    <meta name="apple-mobile-web-app-capable" content="yes">\n    <meta name="apple-mobile-web-app-status-bar-style" content="default">\n    <meta name="apple-mobile-web-app-title" content="리크루팅 DB">\n    <link rel="manifest" href="/manifest.webmanifest">\n    <link rel="icon" href="/static/icons/icon-192.svg" type="image/svg+xml">\n    <link rel="apple-touch-icon" href="/static/icons/icon-192.svg">\n'''
            html = html.replace(marker, pwa_head + marker, 1)
        body_marker = '</body>'
        if body_marker in html and '/sw.js' not in html:
            pwa_script = '''\n    <script>\n      if ('serviceWorker' in navigator) {\n        window.addEventListener('load', () => {\n          navigator.serviceWorker.register('/sw.js', { scope: '/' })\n            .then(reg => console.log('PWA Service Worker 등록 완료:', reg.scope))\n            .catch(err => console.warn('PWA Service Worker 등록 실패:', err));\n        });\n      }\n    </script>\n'''
            html = html.replace(body_marker, pwa_script + body_marker, 1)
        response.set_data(html)
    return response

def init_db():
    try:
        with get_cursor() as cur:
            cur.execute('SELECT 1 FROM candidates LIMIT 1')
        print("✅ candidates 테이블이 존재합니다.")
    except Exception as e:
        print(f"⚠️  candidates 테이블을 확인하세요: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/candidates', methods=['GET'])
def get_candidates():
    try:
        with get_cursor() as cur:
            cur.execute('SELECT * FROM candidates ORDER BY updated_at DESC')
            rows = cur.fetchall()
        return jsonify([serialize(r) for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def find_duplicate(cur, name, exclude_id=None):
    """대소문자 무시로 동일 이름 후보자를 찾습니다. (ILIKE의 %, _ 와일드카드 문제 회피)"""
    if exclude_id is None:
        cur.execute('SELECT * FROM candidates WHERE lower(name) = lower(%s) LIMIT 1', (name.strip(),))
    else:
        cur.execute('SELECT * FROM candidates WHERE lower(name) = lower(%s) AND id <> %s LIMIT 1',
                    (name.strip(), exclude_id))
    return cur.fetchone()


def duplicate_response(duplicate, name):
    return jsonify({
        'duplicate': True,
        'candidate': serialize(duplicate),
        'message': f"'{duplicate.get('name', name)}' 이름의 후보자가 이미 등록되어 있습니다."
    }), 409


@app.route('/api/candidates', methods=['POST'])
def add_candidate():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': '이름은 필수입니다.'}), 400

    contact = data.get('contact', '')
    contact_date = data.get('contact_date', '')
    manager = data.get('manager', '')
    status = data.get('status', '포지션 수락')
    result = data.get('result', '진행 중')
    memo = data.get('memo', '')

    try:
        with get_cursor() as cur:
            # 신규 등록 전에 동일 이름 후보자가 있는지 확인합니다.
            duplicate = find_duplicate(cur, name)
            if duplicate:
                return duplicate_response(duplicate, name)

            cur.execute(
                '''INSERT INTO candidates (name, contact, contact_date, manager, status, result, memo)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                (name, contact, contact_date, manager, status, result, memo)
            )
            new_id = cur.fetchone()['id']
        return jsonify({'id': new_id, 'message': '후보자가 성공적으로 등록되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/candidates/<int:id>', methods=['PUT'])
def update_candidate(id):
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': '이름은 필수입니다.'}), 400

    contact = data.get('contact', '')
    contact_date = data.get('contact_date', '')
    manager = data.get('manager', '')
    status = data.get('status', '')
    result = data.get('result', '')
    memo = data.get('memo', '')

    try:
        with get_cursor() as cur:
            # 수정 시에는 자기 자신은 제외하고 동일 이름 후보자를 확인합니다.
            duplicate = find_duplicate(cur, name, exclude_id=id)
            if duplicate:
                return duplicate_response(duplicate, name)

            cur.execute(
                '''UPDATE candidates
                   SET name=%s, contact=%s, contact_date=%s, manager=%s,
                       status=%s, result=%s, memo=%s, updated_at=%s
                   WHERE id=%s''',
                (name, contact, contact_date, manager, status, result, memo,
                 datetime.now(timezone.utc), id)
            )
            changes = cur.rowcount
        return jsonify({'message': '후보자 정보가 수정되었습니다.', 'changes': changes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/candidates/<int:id>', methods=['DELETE'])
def delete_candidate(id):
    try:
        with get_cursor() as cur:
            cur.execute('DELETE FROM candidates WHERE id = %s', (id,))
            changes = cur.rowcount
        return jsonify({'message': '후보자가 삭제되었습니다.', 'changes': changes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/internal/weekly-backup', methods=['GET'])
def weekly_backup():
    token = request.headers.get('X-Backup-Token', '')
    expected = os.getenv('BACKUP_TRIGGER_TOKEN', '')
    if not expected or token != expected:
        return ('', 404)

    # 성공/실패 여부를 웹앱에 표시하지 않습니다.
    # 외부 스케줄러는 이 엔드포인트를 주 1회 호출하기만 하면 됩니다.
    try:
        run_backup()
    except Exception:
        pass

    return ('', 204)

if __name__ == '__main__':
    init_db()
    print(f"🚀 서버 시작")
    print("📊 PostgreSQL 연결 풀 준비 완료")
    
    port = int(os.environ.get('PORT', 3000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
