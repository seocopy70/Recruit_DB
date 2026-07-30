import os
from flask import Flask, render_template, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

# Supabase 클라이언트 초기화
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

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
            .order('created_at', desc=True) \
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
                'memo': memo
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
    app.run(host='0.0.0.0', port=port, debug=True)