import os
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from supabase import create_client, Client
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

# Supabase 클라이언트 초기화
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

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
    # Supabase는 자동으로 테이블을 생성하지 않으므로 수동으로 확인
    try:
        supabase.table('candidates').select('*').limit(1).execute()
        print("✅ candidates 테이블이 존재합니다.")
    except Exception as e:
        print(f"⚠️  candidates 테이블을 수동으로 생성하세요: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/candidates', methods=['GET'])
def get_candidates():
    try:
        response = supabase.table('candidates') \
            .select('*') \
            .order('updated_at', desc=True) \
            .execute()
        candidates = response.data
        return jsonify(candidates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        response = supabase.table('candidates') \
            .insert({
                'name': name,
                'contact': contact,
                'contact_date': contact_date,
                'manager': manager,
                'status': status,
                'result': result,
                'memo': memo
            }) \
            .execute()
        return jsonify({'id': response.data[0]['id'], 'message': '후보자가 성공적으로 등록되었습니다.'})
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
        response = supabase.table('candidates') \
            .update({
                'name': name,
                'contact': contact,
                'contact_date': contact_date,
                'manager': manager,
                'status': status,
                'result': result,
                'memo': memo,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }) \
            .eq('id', id) \
            .execute()
        return jsonify({'message': '후보자 정보가 수정되었습니다.', 'changes': len(response.data)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/candidates/<int:id>', methods=['DELETE'])
def delete_candidate(id):
    try:
        response = supabase.table('candidates') \
            .delete() \
            .eq('id', id) \
            .execute()
        return jsonify({'message': '후보자가 삭제되었습니다.', 'changes': len(response.data)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    print(f"🚀 서버 시작")
    print(f"📊 Supabase 연결: {supabase_url}")
    
    port = int(os.environ.get('PORT', 3000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
