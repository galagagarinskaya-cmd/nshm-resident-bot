from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from database import Database
    from config import FLASK_PORT, FLASK_HOST, TELEGRAM_ADMIN_IDS
    db = Database()
    logger.info("✅ Database initialized successfully")
except Exception as e:
    logger.error(f"❌ Error initializing database: {e}")
    db = None

app = Flask(__name__)
CORS(app)

# Simple HTML template for admin panel
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>НШМ Бот - Admin Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        h1 { font-size: 28px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .stat-number { font-size: 32px; font-weight: bold; color: #667eea; }
        .stat-label { font-size: 14px; color: #999; margin-top: 5px; }

        table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        th {
            background: #f8f9fa;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #e9ecef;
        }
        td {
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
        }
        tr:hover { background: #f8f9fa; }

        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-danger { background: #f8d7da; color: #721c24; }

        .section {
            margin-bottom: 40px;
        }
        .section-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }

        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover { background: #764ba2; }

        .loading { text-align: center; color: #999; padding: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 НШМ Резидент Бот - Admin Panel</h1>
            <p>Управление резидентами и мониторинг активности</p>
        </header>

        <div class="stats" id="stats">
            <div class="loading">Загрузка статистики...</div>
        </div>

        <div class="section">
            <h2 class="section-title">📊 Список резидентов</h2>
            <table id="residentsTable">
                <thead>
                    <tr>
                        <th>ID Telegram</th>
                        <th>Имя</th>
                        <th>Согласие с правилами</th>
                        <th>Опрос</th>
                        <th>Дата добавления</th>
                    </tr>
                </thead>
                <tbody id="residentsBody">
                    <tr><td colspan="5" class="loading">Загрузка данных...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">📝 Ответы на опросы</h2>
            <table id="surveysTable">
                <thead>
                    <tr>
                        <th>Резидент</th>
                        <th>Блок</th>
                        <th>Вопрос</th>
                        <th>Ответ</th>
                        <th>Дата</th>
                    </tr>
                </thead>
                <tbody id="surveysBody">
                    <tr><td colspan="5" class="loading">Загрузка данных...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                const html = `
                    <div class="stat-card">
                        <div class="stat-number">${data.total_residents}</div>
                        <div class="stat-label">Всего резидентов</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.rules_accepted}</div>
                        <div class="stat-label">Согласили с правилами</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.survey_completed}</div>
                        <div class="stat-label">Прошли опрос</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.survey_pending}</div>
                        <div class="stat-label">Ожидают опроса</div>
                    </div>
                `;
                document.getElementById('stats').innerHTML = html;
            } catch (e) {
                console.error('Error loading stats:', e);
            }
        }

        async function loadResidents() {
            try {
                const res = await fetch('/api/residents');
                const data = await res.json();

                const rows = data.residents.map(r => `
                    <tr>
                        <td>${r.user_id}</td>
                        <td>${r.first_name} ${r.last_name || ''}</td>
                        <td>${r.rules_accepted ? '<span class="badge badge-success">✓ Да</span>' : '<span class="badge badge-danger">✗ Нет</span>'}</td>
                        <td>${r.survey_completed ? '<span class="badge badge-success">✓ Завершен</span>' : r.survey_sent ? '<span class="badge badge-warning">⏳ Отправлен</span>' : '<span class="badge badge-danger">⊘ Не отправлен</span>'}</td>
                        <td>${new Date(r.created_at).toLocaleDateString('ru-RU')}</td>
                    </tr>
                `).join('');

                document.getElementById('residentsBody').innerHTML = rows;
            } catch (e) {
                console.error('Error loading residents:', e);
            }
        }

        // Load data on page load
        window.addEventListener('load', () => {
            loadStats();
            loadResidents();
            setInterval(loadStats, 30000); // Refresh stats every 30s
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(ADMIN_TEMPLATE)

@app.route('/api/stats')
def get_stats():
    """Get bot statistics"""
    if not db:
        return jsonify({
            "total_residents": 0,
            "rules_accepted": 0,
            "survey_completed": 0,
            "survey_pending": 0,
            "error": "Database not initialized"
        }), 503

    import sqlite3
    try:
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE rules_accepted = 1")
        rules = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE survey_completed = 1")
        survey_done = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE survey_sent = 1 AND survey_completed = 0")
        survey_pending = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "total_residents": total,
            "rules_accepted": rules,
            "survey_completed": survey_done,
            "survey_pending": survey_pending
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/residents')
def get_residents():
    """Get all residents"""
    if not db:
        return jsonify({"residents": [], "error": "Database not initialized"}), 503

    import sqlite3
    try:
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
        residents = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({"residents": residents})
    except Exception as e:
        logger.error(f"Error getting residents: {e}")
        return jsonify({"residents": [], "error": str(e)}), 500

@app.route('/api/surveys/<int:user_id>')
def get_user_surveys(user_id: int):
    """Get survey responses for user"""
    responses = db.get_survey_responses(user_id)
    return jsonify({"responses": responses})

def run_admin_panel(port=None):
    """Run admin panel"""
    import os
    # Use Railway PORT env var if available, otherwise use configured FLASK_PORT
    port = port or int(os.getenv("PORT", FLASK_PORT))
    print(f"Starting Admin Panel on http://{FLASK_HOST}:{port}")
    app.run(host=FLASK_HOST, port=port, debug=False, threaded=True)

if __name__ == "__main__":
    run_admin_panel()
