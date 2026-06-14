import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request
from extractor import scan_documents

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'project_data.db')

ITEM_TYPES = ['milestones', 'tasks', 'todos', 'build_notes', 'statuses', 'opens', 'pendings', 'iso20022s']

TYPE_MAP = {
    'milestone': 'milestones',
    'task': 'tasks',
    'todo': 'todos',
    'build_note': 'build_notes',
    'status': 'statuses',
    'open': 'opens',
    'pending': 'pendings',
    'iso20022': 'iso20022s',
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            file TEXT NOT NULL,
            date TEXT NOT NULL,
            scanned_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at TEXT NOT NULL,
            item_count INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_items(items):
    scanned_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM items')
    conn.executemany(
        'INSERT INTO items (project, type, content, file, date, scanned_at) VALUES (?, ?, ?, ?, ?, ?)',
        [(i['project'], i['type'], i.get('content', ''), i['file'], i['date'], scanned_at) for i in items]
    )
    conn.execute('INSERT INTO scan_log (scanned_at, item_count) VALUES (?, ?)', (scanned_at, len(items)))
    conn.commit()
    conn.close()

def load_items():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('SELECT project, type, content, file, date FROM items ORDER BY project, type').fetchall()
    last_scan = conn.execute('SELECT scanned_at FROM scan_log ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return [dict(r) for r in rows], (last_scan['scanned_at'] if last_scan else None)

def get_items(refresh=False):
    if refresh:
        items = scan_documents()
        save_items(items)
        return items, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    items, last_scan = load_items()
    if not items:
        items = scan_documents()
        save_items(items)
        _, last_scan = load_items()
    return items, last_scan

def group_items(items):
    projects = {}
    for item in items:
        project = item['project']
        item_type = item['type']
        bucket = TYPE_MAP.get(item_type)
        if not bucket:
            continue
        if project not in projects:
            projects[project] = {t: [] for t in ITEM_TYPES}
        projects[project][bucket].append(item)
    return projects

@app.route('/')
def dashboard():
    refresh = request.args.get('refresh') == '1'
    items, last_scan = get_items(refresh=refresh)
    projects = group_items(items)
    return render_template('dashboard.html', projects=projects, last_scan=last_scan)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
