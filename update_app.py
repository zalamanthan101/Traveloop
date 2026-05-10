import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Imports
code = code.replace("import sqlite3, hashlib, os, json", "import sqlite3, bcrypt, os, json")

# 2. Schema changes
users_old = """        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            photo TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );"""
users_new = """        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            photo TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );"""
code = code.replace(users_old, users_new)

notes_old = """        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            stop_id INTEGER,
            content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        );"""
notes_new = notes_old + """
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            region TEXT,
            cost_index INTEGER DEFAULT 50,
            popularity_score INTEGER DEFAULT 50,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS city_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            cost REAL DEFAULT 0,
            duration_hours REAL DEFAULT 1,
            description TEXT,
            FOREIGN KEY(city_id) REFERENCES cities(id)
        );
        CREATE TABLE IF NOT EXISTS budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            estimated_cost REAL DEFAULT 0,
            actual_cost REAL DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id)
        );"""
code = code.replace(notes_old, notes_new)

# 3. Seed data
seed_old = """    try:
        pw = hashlib.sha256('demo123'.encode()).hexdigest()
        c.execute("INSERT OR IGNORE INTO users (name, email, password) VALUES (?, ?, ?)",
                  ('Alex Wanderer', 'demo@traveloop.com', pw))"""
seed_new = """    try:
        # Use simple hash for demo initially so we don't slow down startup, but we're changing to bcrypt
        pw = bcrypt.hashpw('demo123'.encode(), bcrypt.gensalt()).decode()
        c.execute("INSERT OR IGNORE INTO users (name, email, password, is_admin) VALUES (?, ?, ?, ?)",
                  ('Alex Wanderer', 'demo@traveloop.com', pw, 1))"""
code = code.replace(seed_old, seed_new)

seed_cities = """
        # Seed cities
        if c.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 0:
            cities_data = [
                ('Paris', 'France', 'Europe', 85, 95, 'City of light'),
                ('Rome', 'Italy', 'Europe', 75, 90, 'Eternal city'),
                ('Tokyo', 'Japan', 'Asia', 80, 95, 'Neon streets'),
                ('Bali', 'Indonesia', 'Asia', 40, 85, 'Island paradise')
            ]
            for cd in cities_data:
                c.execute("INSERT INTO cities (name, country, region, cost_index, popularity_score, description) VALUES (?,?,?,?,?,?)", cd)
            conn.commit()
"""
code = code.replace("for s in stops_data:", seed_cities + "                for s in stops_data:")

# 4. Auth helpers
code = code.replace("def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()",
                    "def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()\ndef check_pw(p, hashed): return bcrypt.checkpw(p.encode(), hashed.encode())")

# 5. Login check
login_old = """            user = conn.execute("SELECT * FROM users WHERE email=? AND password=?",
                                (email, hash_pw(password))).fetchone()
            conn.close()
            if user:"""
login_new = """            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            
            if user and check_pw(password, user['password']):
                conn.close()"""
code = code.replace(login_old, login_new)

# 6. Delete trip
delete_old = "conn.execute(\"DELETE FROM trips WHERE id=? AND user_id=?\", (trip_id, session['user_id']))"
delete_new = "conn.execute(\"DELETE FROM budget_items WHERE trip_id=?\", (trip_id,))\n    " + delete_old
code = code.replace(delete_old, delete_new)

# 7. Add new routes at the end before if __name__ == '__main__':
new_routes = """
# ─── NEW PRD ROUTES ───────────────────────────────────────────────────────────

@app.route('/cities/search')
@login_required
def search_cities_page():
    return render_template('search_cities.html')

@app.route('/api/cities/search')
@login_required
def api_search_cities():
    q = request.args.get('q', '')
    conn = get_db()
    if q:
        cities = conn.execute("SELECT * FROM cities WHERE name LIKE ? OR country LIKE ? LIMIT 20", (f'%{q}%', f'%{q}%')).fetchall()
    else:
        cities = conn.execute("SELECT * FROM cities ORDER BY popularity_score DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify([dict(c) for c in cities])

@app.route('/activities/search')
@login_required
def search_activities_page():
    return render_template('search_activities.html')

@app.route('/api/activities/search')
@login_required
def api_search_activities():
    city_id = request.args.get('city_id')
    q = request.args.get('q', '')
    conn = get_db()
    query = "SELECT * FROM city_activities WHERE 1=1"
    params = []
    if city_id:
        query += " AND city_id=?"
        params.append(city_id)
    if q:
        query += " AND name LIKE ?"
        params.append(f'%{q}%')
    query += " LIMIT 50"
    activities = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(a) for a in activities])

@app.route('/api/stops/reorder', methods=['POST'])
@login_required
def reorder_stops():
    d = request.json # expected { trip_id: 1, stops: [id1, id2, ...] }
    trip_id = d.get('trip_id')
    stop_ids = d.get('stops', [])
    conn = get_db()
    trip = conn.execute("SELECT id FROM trips WHERE id=? AND user_id=?", (trip_id, session['user_id'])).fetchone()
    if not trip:
        conn.close()
        return jsonify({'error': 'unauthorized'}), 403
    for i, sid in enumerate(stop_ids):
        conn.execute("UPDATE stops SET position=? WHERE id=? AND trip_id=?", (i, sid, trip_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/share/<int:trip_id>/copy', methods=['POST'])
@login_required
def copy_trip(trip_id):
    conn = get_db()
    src_trip = conn.execute("SELECT * FROM trips WHERE id=? AND is_public=1", (trip_id,)).fetchone()
    if not src_trip:
        conn.close()
        return redirect(url_for('dashboard'))
    
    uid = session['user_id']
    cur = conn.execute("INSERT INTO trips (user_id, name, description, start_date, end_date, cover, is_public, total_budget) VALUES (?,?,?,?,?,?,?,?)",
                       (uid, src_trip['name'] + ' (Copy)', src_trip['description'], src_trip['start_date'], src_trip['end_date'], src_trip['cover'], 0, src_trip['total_budget']))
    new_tid = cur.lastrowid
    
    stops = conn.execute("SELECT * FROM stops WHERE trip_id=?", (trip_id,)).fetchall()
    for s in stops:
        scur = conn.execute("INSERT INTO stops (trip_id, city, country, start_date, end_date, position) VALUES (?,?,?,?,?,?)",
                            (new_tid, s['city'], s['country'], s['start_date'], s['end_date'], s['position']))
        new_sid = scur.lastrowid
        acts = conn.execute("SELECT * FROM activities WHERE stop_id=?", (s['id'],)).fetchall()
        for a in acts:
            conn.execute("INSERT INTO activities (stop_id, name, type, cost, duration, description) VALUES (?,?,?,?,?,?)",
                         (new_sid, a['name'], a['type'], a['cost'], a['duration'], a['description']))
                         
    # Also copy budget items
    bis = conn.execute("SELECT * FROM budget_items WHERE trip_id=?", (trip_id,)).fetchall()
    for b in bis:
        conn.execute("INSERT INTO budget_items (trip_id, category, estimated_cost, actual_cost) VALUES (?,?,?,?)",
                     (new_tid, b['category'], b['estimated_cost'], b['actual_cost']))
                     
    conn.commit()
    conn.close()
    flash('Trip copied successfully!')
    return redirect(url_for('itinerary_builder', trip_id=new_tid))

@app.route('/admin')
@login_required
def admin_dashboard():
    conn = get_db()
    user = conn.execute("SELECT is_admin FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if not user or not user['is_admin']:
        conn.close()
        return redirect(url_for('dashboard'))
        
    stats = {}
    stats['users'] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    stats['trips'] = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    stats['public_trips'] = conn.execute("SELECT COUNT(*) FROM trips WHERE is_public=1").fetchone()[0]
    
    top_cities = conn.execute("SELECT city, COUNT(*) as count FROM stops GROUP BY city ORDER BY count DESC LIMIT 10").fetchall()
    conn.close()
    return render_template('admin.html', stats=stats, top_cities=top_cities)

@app.route('/api/profile/delete', methods=['POST'])
@login_required
def delete_profile():
    conn = get_db()
    uid = session['user_id']
    # Delete everything related to user
    trips = conn.execute("SELECT id FROM trips WHERE user_id=?", (uid,)).fetchall()
    for t in trips:
        tid = t['id']
        conn.execute("DELETE FROM activities WHERE stop_id IN (SELECT id FROM stops WHERE trip_id=?)", (tid,))
        conn.execute("DELETE FROM stops WHERE trip_id=?", (tid,))
        conn.execute("DELETE FROM checklist WHERE trip_id=?", (tid,))
        conn.execute("DELETE FROM notes WHERE trip_id=?", (tid,))
        conn.execute("DELETE FROM budget_items WHERE trip_id=?", (tid,))
    conn.execute("DELETE FROM trips WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/budget_items', methods=['POST'])
@login_required
def add_budget_item():
    d = request.json
    conn = get_db()
    trip = conn.execute("SELECT * FROM trips WHERE id=? AND user_id=?", (d['trip_id'], session['user_id'])).fetchone()
    if not trip:
        conn.close()
        return jsonify({'error': 'unauthorized'}), 403
    
    cur = conn.execute("INSERT INTO budget_items (trip_id, category, estimated_cost) VALUES (?,?,?)",
                       (d['trip_id'], d['category'], float(d.get('estimated_cost',0))))
    conn.commit()
    bid = cur.lastrowid
    conn.close()
    return jsonify({'id': bid, 'category': d['category'], 'estimated_cost': float(d.get('estimated_cost',0))})
    
@app.route('/api/budget_items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_budget_item(item_id):
    conn = get_db()
    conn.execute("DELETE FROM budget_items WHERE id=? AND trip_id IN (SELECT id FROM trips WHERE user_id=?)", (item_id, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
"""
code = code.replace("if __name__ == '__main__':", new_routes + "\nif __name__ == '__main__':")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("app.py updated successfully.")
