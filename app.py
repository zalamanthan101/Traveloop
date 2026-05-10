from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import bcrypt, os, json
from urllib.request import urlopen
from datetime import datetime, date
from functools import wraps
from groq import Groq
from dotenv import load_dotenv
import psycopg2 
import psycopg2.extras

# .env file se variables load karna
load_dotenv()

# .env se DATABASE_URL fetch karna
db_url = os.getenv("DATABASE_URL")

# Groq Setup
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

app = Flask(__name__)
app.secret_key = 'traveloop_secret_2024'

CURRENCIES = [
    {'code': 'USD', 'symbol': '$', 'label': 'USD - US Dollar'},
    {'code': 'INR', 'symbol': '₹', 'label': 'INR - Indian Rupee'},
    {'code': 'EUR', 'symbol': '€', 'label': 'EUR - Euro'},
    {'code': 'GBP', 'symbol': '£', 'label': 'GBP - British Pound'},
    {'code': 'JPY', 'symbol': '¥', 'label': 'JPY - Japanese Yen'},
    {'code': 'AUD', 'symbol': 'A$', 'label': 'AUD - Australian Dollar'},
    {'code': 'CAD', 'symbol': 'CA$', 'label': 'CAD - Canadian Dollar'},
    {'code': 'SGD', 'symbol': 'S$', 'label': 'SGD - Singapore Dollar'},
    {'code': 'AED', 'symbol': 'AED ', 'label': 'AED - UAE Dirham'},
]

FALLBACK_EXCHANGE_RATES = {
    'USD': 1, 'INR': 83.5, 'EUR': 0.92, 'GBP': 0.79, 'JPY': 155,
    'AUD': 1.52, 'CAD': 1.36, 'SGD': 1.35, 'AED': 3.67,
}

# ─── DB SETUP ─────────────────────────────────────────────────────────────────

def get_db():
    conn = psycopg2.connect(db_url)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def get_currency_setting():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key='currency'")
    code = cur.fetchone()
    conn.close()
    selected = code['value'] if code else 'USD'
    currency = dict(next((c for c in CURRENCIES if c['code'] == selected), CURRENCIES[0]))
    currency['rate'] = get_exchange_rate(currency['code'])
    return currency

def get_exchange_rate(code):
    rates = get_exchange_rates()
    return float(rates.get(code, FALLBACK_EXCHANGE_RATES.get(code, 1)))

def get_exchange_rates():
    try:
        with urlopen('https://open.er-api.com/v6/latest/USD', timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
        rates = data.get('rates', {})
        if data.get('result') == 'success' and rates:
            return {code: float(rates.get(code, fallback)) for code, fallback in FALLBACK_EXCHANGE_RATES.items()}
    except Exception:
        pass
    return FALLBACK_EXCHANGE_RATES

def set_currency_setting(code):
    if not any(c['code'] == code for c in CURRENCIES):
        return False
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO app_settings (key, value) VALUES ('currency', %s)
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value
    """, (code,))
    conn.commit()
    cur.close()
    conn.close()
    return True

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            photo TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS trips (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            cover TEXT DEFAULT '',
            is_public INTEGER DEFAULT 0,
            total_budget REAL DEFAULT 0,
            trip_type TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stops (
            id SERIAL PRIMARY KEY,
            trip_id INTEGER NOT NULL,
            city TEXT NOT NULL,
            country TEXT,
            start_date TEXT,
            end_date TEXT,
            position INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS activities (
            id SERIAL PRIMARY KEY,
            stop_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT,
            cost REAL DEFAULT 0,
            duration TEXT,
            description TEXT,
            FOREIGN KEY(stop_id) REFERENCES stops(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS checklist (
            id SERIAL PRIMARY KEY,
            trip_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            packed INTEGER DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            trip_id INTEGER NOT NULL,
            stop_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cities (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            region TEXT,
            cost_index INTEGER DEFAULT 50,
            popularity_score INTEGER DEFAULT 50,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS city_activities (
            id SERIAL PRIMARY KEY,
            city_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            cost REAL DEFAULT 0,
            duration_hours REAL DEFAULT 1,
            description TEXT,
            FOREIGN KEY(city_id) REFERENCES cities(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS budget_items (
            id SERIAL PRIMARY KEY,
            trip_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            estimated_cost REAL DEFAULT 0,
            actual_cost REAL DEFAULT 0,
            FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')
    conn.commit()
    c.execute("INSERT INTO app_settings (key, value) VALUES ('currency', 'USD') ON CONFLICT(key) DO NOTHING")
    conn.commit()
    
    # ─── DB MIGRATIONS ─────────────────
    migrations = [
        "ALTER TABLE trips ADD COLUMN trip_type TEXT DEFAULT 'general'",
    ]
    for migration in migrations:
        try:
            c.execute(migration)
            conn.commit()
        except:
            conn.rollback()  # Postgres needs rollback on failed query
            pass
            
    # seed demo and admin users
    try:
        pw = hash_pw('demo123')
        admin_pw = hash_pw('admin123')
        c.execute("INSERT INTO users (name, email, password, is_admin) VALUES (%s, %s, %s, %s) ON CONFLICT(email) DO NOTHING",
                  ('Alex Wanderer', 'demo@traveloop.com', pw, 0))
        c.execute("INSERT INTO users (name, email, password, is_admin) VALUES (%s, %s, %s, %s) ON CONFLICT(email) DO NOTHING",
                  ('Traveloop Admin', 'admin@traveloop.com', admin_pw, 1))
        c.execute("UPDATE users SET is_admin=0 WHERE email='demo@traveloop.com'")
        c.execute("UPDATE users SET is_admin=1 WHERE email='admin@traveloop.com'")
        conn.commit()
        
        c.execute("SELECT id FROM users WHERE email='demo@traveloop.com'")
        user = c.fetchone()
        
        if user:
            uid = user['id']
            # Check if demo trip already exists to avoid duplicates
            c.execute("SELECT id FROM trips WHERE user_id=%s AND name='Europe Grand Tour'", (uid,))
            trip = c.fetchone()
            if not trip:
                c.execute("""
                    INSERT INTO trips (user_id, name, description, start_date, end_date, is_public, total_budget) 
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """, (uid, 'Europe Grand Tour', 'A 2-week adventure across Europe', '2024-06-01', '2024-06-15', 1, 3200))
                tid = c.fetchone()['id']
                conn.commit()
                
                stops_data = [
                    (tid, 'Paris', 'France', '2024-06-01', '2024-06-04', 0),
                    (tid, 'Rome', 'Italy', '2024-06-04', '2024-06-09', 1),
                    (tid, 'Barcelona', 'Spain', '2024-06-09', '2024-06-15', 2),
                ]
                for s in stops_data:
                    c.execute("INSERT INTO stops (trip_id, city, country, start_date, end_date, position) VALUES (%s,%s,%s,%s,%s,%s)", s)
                conn.commit()
                
        c.execute("SELECT COUNT(*) as cnt FROM cities")
        if c.fetchone()['cnt'] == 0:
            cities_data = [
                ('Paris', 'France', 'Europe', 85, 95, 'City of light'),
                ('Rome', 'Italy', 'Europe', 75, 90, 'Eternal city'),
                ('Tokyo', 'Japan', 'Asia', 80, 95, 'Neon streets'),
                ('Bali', 'Indonesia', 'Asia', 40, 85, 'Island paradise')
            ]
            for cd in cities_data:
                c.execute("INSERT INTO cities (name, country, region, cost_index, popularity_score, description) VALUES (%s,%s,%s,%s,%s,%s)", cd)
            conn.commit()

    except Exception as e:
        conn.rollback()
        pass
        
    c.close()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            return redirect(url_for('dashboard'))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT is_admin FROM users WHERE id=%s", (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user or not user['is_admin']:
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def delete_user_data(conn, uid):
    cur = conn.cursor()
    cur.execute("SELECT id FROM trips WHERE user_id=%s", (uid,))
    trips = cur.fetchall()
    for t in trips:
        delete_trip_data(conn, t['id'])
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
    cur.close()

def delete_trip_data(conn, trip_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM activities WHERE stop_id IN (SELECT id FROM stops WHERE trip_id=%s)", (trip_id,))
    cur.execute("DELETE FROM stops WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM checklist WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM notes WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM budget_items WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM trips WHERE id=%s", (trip_id,))
    cur.close()

def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pw(p, hashed): return bcrypt.checkpw(p.encode(), hashed.encode())

# ─── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('welcome.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email','').strip()
        password = request.form.get('password','')
        conn = get_db()
        cur = conn.cursor()
        
        if action == 'login':
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
            
            if user and check_pw(password, user['password']):
                cur.close()
                conn.close()
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['is_admin'] = bool(user['is_admin'])
                if session['is_admin']:
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('dashboard'))
            cur.close()
            conn.close()
            error = 'Invalid email or password'
            
        elif action == 'signup':
            name = request.form.get('name','').strip()
            try:
                cur.execute("INSERT INTO users (name, email, password) VALUES (%s,%s,%s) RETURNING id, name",
                             (name, email, hash_pw(password)))
                conn.commit()
                user = cur.fetchone()
                cur.close()
                conn.close()
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['is_admin'] = False
                return redirect(url_for('dashboard'))
            except Exception as e:
                conn.rollback()
                cur.close()
                conn.close()
                error = 'Email already registered'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cur = conn.cursor()
    uid = session['user_id']
    cur.execute("SELECT * FROM trips WHERE user_id=%s ORDER BY created_at DESC LIMIT 6", (uid,))
    trips = cur.fetchall()
    
    cur.execute("SELECT COUNT(*) as cnt FROM trips WHERE user_id=%s", (uid,))
    total_trips = cur.fetchone()['cnt']
    
    cur.execute("""SELECT COUNT(DISTINCT s.city) as cnt FROM stops s
                   JOIN trips t ON s.trip_id=t.id WHERE t.user_id=%s""", (uid,))
    total_cities = cur.fetchone()['cnt']
    
    cur.execute("SELECT * FROM trips WHERE user_id=%s AND CAST(start_date AS DATE) >= CURRENT_DATE ORDER BY start_date LIMIT 3", (uid,))
    upcoming = cur.fetchall()
    
    cur.execute("""
        SELECT name, country, region, popularity_score
        FROM cities
        ORDER BY popularity_score DESC, name ASC
        LIMIT 6
    """)
    city_rows = cur.fetchall()
    cur.close()
    conn.close()
    
    emojis = ['🌍', '🗺️', '🏖️', '🏔️', '🏙️', '✈️']
    destinations = []
    for i, city in enumerate(city_rows):
        score = city['popularity_score'] or 0
        if score >= 90:
            tag = 'Trending'
        elif score >= 75:
            tag = 'Popular'
        else:
            tag = city['region'] or 'Explore'
        destinations.append({
            'city': city['name'],
            'country': city['country'],
            'emoji': emojis[i % len(emojis)],
            'temp': f"Pop {score}/100",
            'tag': tag,
        })
    return render_template('dashboard.html', trips=trips, total_trips=total_trips,
                           total_cities=total_cities, upcoming=upcoming, destinations=destinations)

# ─── TRIPS ────────────────────────────────────────────────────────────────────

@app.route('/trips')
@login_required
def my_trips():
    conn = get_db()
    cur = conn.cursor()
    uid = session['user_id']
    cur.execute("SELECT t.*, (SELECT COUNT(*) FROM stops WHERE trip_id=t.id) as stop_count FROM trips t WHERE user_id=%s ORDER BY created_at DESC", (uid,))
    trips = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('trips.html', trips=trips)

@app.route('/trips/new', methods=['GET','POST'])
@login_required
def create_trip():
    if request.method == 'POST':
        uid = session['user_id']
        name = request.form.get('name','').strip()
        desc = request.form.get('description','')
        start = request.form.get('start_date','')
        end = request.form.get('end_date','')
        budget = request.form.get('budget', 0) or 0
        trip_type = request.form.get('trip_type', 'general')
   
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT INTO trips (user_id, name, description, start_date, end_date, total_budget, trip_type) 
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                           (uid, name, desc, start, end, float(budget), trip_type))
        tid = cur.fetchone()['id']
        conn.commit()
        
        # Smart packing
        PACKING_PRESETS = {
            'general': [('Passport','documents'),('Travel Insurance','documents'),('Phone Charger','electronics'),('Universal Adapter','electronics'),('Sunscreen','toiletries'),('Comfortable Shoes','clothing'),('First Aid Kit','medicines'),('Cash/Cards','general')],
            'beach': [('Passport','documents'),('Sunscreen SPF 50+','toiletries'),('Swimsuit','clothing'),('Flip Flops','clothing'),('Beach Towel','general'),('Sunglasses','general'),('After-sun lotion','toiletries'),('Waterproof bag','general'),('Snorkel gear','general')],
            'mountains': [('Passport','documents'),('Hiking Boots','clothing'),('Warm Jacket','clothing'),('Thermal Socks','clothing'),('Trekking Poles','general'),('Headlamp','electronics'),('Energy Bars','general'),('First Aid Kit','medicines'),('Water Bottle','general'),('Raincoat','clothing')],
            'city': [('Passport','documents'),('Travel Card/Metro Pass','documents'),('Comfortable Sneakers','clothing'),('Day Bag/Backpack','general'),('Camera','electronics'),('Power Bank','electronics'),('City Map/Offline Maps','general'),('Umbrella','general')],
            'business': [('Passport','documents'),('Business Cards','documents'),('Laptop','electronics'),('Laptop Charger','electronics'),('Formal Attire','clothing'),('Dress Shoes','clothing'),('Presentation Materials','documents'),('Power Bank','electronics')],
            'adventure': [('Passport','documents'),('Tent','general'),('Sleeping Bag','general'),('Hiking Boots','clothing'),('Rope','general'),('First Aid Kit','medicines'),('Water Purification Tablets','medicines'),('Headlamp','electronics'),('Multi-tool','general'),('Raincoat','clothing')]
        }
        items = PACKING_PRESETS.get(trip_type, PACKING_PRESETS['general'])
        for item, cat in items:
            cur.execute("INSERT INTO checklist (trip_id, item, category) VALUES (%s,%s,%s)", (tid, item, cat))
        conn.commit()
        
        cur.close()
        conn.close()
        return redirect(url_for('itinerary_builder', trip_id=tid))
    return render_template('create_trip.html')

@app.route('/trips/<int:trip_id>/delete', methods=['POST'])
@login_required
def delete_trip(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM activities WHERE stop_id IN (SELECT id FROM stops WHERE trip_id=%s)", (trip_id,))
    cur.execute("DELETE FROM stops WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM checklist WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM notes WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM budget_items WHERE trip_id=%s", (trip_id,))
    cur.execute("DELETE FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('my_trips'))

# ─── ITINERARY ────────────────────────────────────────────────────────────────

@app.route('/trips/<int:trip_id>/builder', methods=['GET','POST'])
@login_required
def itinerary_builder(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return redirect(url_for('my_trips'))
    
    cur.execute("SELECT * FROM stops WHERE trip_id=%s ORDER BY position", (trip_id,))
    stops = cur.fetchall()
    stops_with_acts = []
    for s in stops:
        cur.execute("SELECT * FROM activities WHERE stop_id=%s", (s['id'],))
        acts = cur.fetchall()
        stops_with_acts.append({'stop': s, 'activities': acts})
        
    cur.close()
    conn.close()
    return render_template('builder.html', trip=trip, stops=stops_with_acts)

@app.route('/trips/<int:trip_id>/view')
def itinerary_view(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s", (trip_id,))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return redirect(url_for('dashboard'))
    if not trip['is_public'] and session.get('user_id') != trip['user_id']:
        cur.close(); conn.close(); return redirect(url_for('dashboard'))
        
    cur.execute("SELECT * FROM stops WHERE trip_id=%s ORDER BY position", (trip_id,))
    stops = cur.fetchall()
    stops_with_acts = []
    total_cost = 0
    for s in stops:
        cur.execute("SELECT * FROM activities WHERE stop_id=%s", (s['id'],))
        acts = cur.fetchall()
        stop_cost = sum(a['cost'] for a in acts)
        total_cost += stop_cost
        stops_with_acts.append({'stop': s, 'activities': acts, 'cost': stop_cost})
        
    cur.close()
    conn.close()
    return render_template('itinerary_view.html', trip=trip, stops=stops_with_acts, total_cost=total_cost)

# ─── STOPS API ────────────────────────────────────────────────────────────────

@app.route('/api/stops', methods=['POST'])
@login_required
def add_stop():
    d = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (d['trip_id'], session['user_id']))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return jsonify({'error': 'unauthorized'}), 403
    
    cur.execute("SELECT COUNT(*) as cnt FROM stops WHERE trip_id=%s", (d['trip_id'],))
    pos = cur.fetchone()['cnt']
    
    cur.execute("""INSERT INTO stops (trip_id, city, country, start_date, end_date, position) 
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (d['trip_id'], d['city'], d.get('country',''), d.get('start_date',''), d.get('end_date',''), pos))
    sid = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': sid, 'city': d['city'], 'country': d.get('country',''), 'position': pos})

@app.route('/api/stops/<int:stop_id>', methods=['DELETE'])
@login_required
def delete_stop(stop_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM activities WHERE stop_id=%s", (stop_id,))
    cur.execute("DELETE FROM stops WHERE id=%s", (stop_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/activities', methods=['POST'])
@login_required
def add_activity():
    d = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""INSERT INTO activities (stop_id, name, type, cost, duration, description) 
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (d['stop_id'], d['name'], d.get('type','sightseeing'), float(d.get('cost',0)), d.get('duration',''), d.get('description','')))
    aid = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': aid, 'name': d['name'], 'cost': float(d.get('cost',0)), 'type': d.get('type','sightseeing')})

@app.route('/api/activities/<int:act_id>', methods=['DELETE'])
@login_required
def delete_activity(act_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM activities WHERE id=%s", (act_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

# ─── BUDGET ───────────────────────────────────────────────────────────────────

@app.route('/trips/<int:trip_id>/budget')
@login_required
def budget(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return redirect(url_for('my_trips'))
    
    cur.execute("SELECT * FROM stops WHERE trip_id=%s ORDER BY position", (trip_id,))
    stops = cur.fetchall()
    breakdown = []
    total = 0
    for s in stops:
        cur.execute("SELECT * FROM activities WHERE stop_id=%s", (s['id'],))
        acts = cur.fetchall()
        cost = sum(a['cost'] for a in acts)
        total += cost
        breakdown.append({'city': s['city'], 'cost': cost, 'activities': acts})
    
    cur.execute("SELECT * FROM budget_items WHERE trip_id=%s", (trip_id,))
    budget_items = cur.fetchall()
    for bi in budget_items:
        total += bi['estimated_cost']

    COUNTRY_CURRENCY = {
        'France': ('EUR', '€'), 'Germany': ('EUR', '€'), 'Italy': ('EUR', '€'), 'Spain': ('EUR', '€'),
        'UK': ('GBP', '£'), 'India': ('INR', '₹'), 'Japan': ('JPY', '¥'), 'USA': ('USD', '$')
        # Add rest here
    }
    auto_currency = 'USD'
    auto_symbol = '$'
    if stops:
        first_country = stops[0]['country'] if stops[0]['country'] else ''
        if first_country in COUNTRY_CURRENCY:
            auto_currency, auto_symbol = COUNTRY_CURRENCY[first_country]

    cur.close()
    conn.close()
    return render_template('budget.html', trip=trip, breakdown=breakdown, total=total,
                           budget_items=budget_items, auto_currency=auto_currency,
                           auto_symbol=auto_symbol, exchange_rates=get_exchange_rates())

# ─── CHECKLIST ────────────────────────────────────────────────────────────────

@app.route('/trips/<int:trip_id>/checklist', methods=['GET','POST'])
@login_required
def checklist(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if request.method == 'POST':
        item = request.form.get('item','').strip()
        cat = request.form.get('category','general')
        if item:
            cur.execute("INSERT INTO checklist (trip_id, item, category) VALUES (%s,%s,%s)", (trip_id, item, cat))
            conn.commit()
            
    cur.execute("SELECT * FROM checklist WHERE trip_id=%s ORDER BY category, id", (trip_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('checklist.html', trip=trip, items=items)

@app.route('/api/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM checklist WHERE id=%s", (item_id,))
    item = cur.fetchone()
    cur.execute("UPDATE checklist SET packed=%s WHERE id=%s", (0 if item['packed'] else 1, item_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/checklist/<int:item_id>', methods=['DELETE'])
@login_required
def delete_checklist(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM checklist WHERE id=%s", (item_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

# ─── NOTES ────────────────────────────────────────────────────────────────────

@app.route('/trips/<int:trip_id>/notes', methods=['GET','POST'])
@login_required
def notes(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if request.method == 'POST':
        content = request.form.get('content','').strip()
        if content:
            cur.execute("INSERT INTO notes (trip_id, content) VALUES (%s,%s)", (trip_id, content))
            conn.commit()
            
    cur.execute("SELECT * FROM notes WHERE trip_id=%s ORDER BY created_at DESC", (trip_id,))
    all_notes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('notes.html', trip=trip, notes=all_notes)

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=%s", (note_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

# ─── PROFILE ──────────────────────────────────────────────────────────────────

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        cur.execute("UPDATE users SET name=%s WHERE id=%s", (name, session['user_id']))
        conn.commit()
        session['user_name'] = name
        flash('Profile updated!')
    cur.close()
    conn.close()
    return render_template('profile.html', user=user)

# ─── PUBLIC SHARE ─────────────────────────────────────────────────────────────

@app.route('/share/<int:trip_id>')
def public_trip(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT t.*, u.name as author FROM trips t JOIN users u ON t.user_id=u.id WHERE t.id=%s AND t.is_public=1", (trip_id,))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return "Trip not found or not public", 404
    
    cur.execute("SELECT * FROM stops WHERE trip_id=%s ORDER BY position", (trip_id,))
    stops = cur.fetchall()
    stops_with_acts = []
    total_cost = 0
    for s in stops:
        cur.execute("SELECT * FROM activities WHERE stop_id=%s", (s['id'],))
        acts = cur.fetchall()
        cost = sum(a['cost'] for a in acts)
        total_cost += cost
        stops_with_acts.append({'stop': s, 'activities': acts, 'cost': cost})
        
    cur.close()
    conn.close()
    return render_template('public_view.html', trip=trip, stops=stops_with_acts, total_cost=total_cost)

@app.route('/api/trips/<int:trip_id>/toggle-public', methods=['POST'])
@login_required
def toggle_public(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    cur.execute("UPDATE trips SET is_public=%s WHERE id=%s", (0 if trip['is_public'] else 1, trip_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'is_public': not trip['is_public']})

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
    cur = conn.cursor()
    if q:
        cur.execute("SELECT * FROM cities WHERE name LIKE %s OR country LIKE %s LIMIT 20", (f'%{q}%', f'%{q}%'))
        cities = cur.fetchall()
    else:
        cur.execute("SELECT * FROM cities ORDER BY popularity_score DESC LIMIT 20")
        cities = cur.fetchall()
    cur.close()
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
    cur = conn.cursor()
    query = "SELECT * FROM city_activities WHERE 1=1"
    params = []
    if city_id:
        query += " AND city_id=%s"
        params.append(city_id)
    if q:
        query += " AND name LIKE %s"
        params.append(f'%{q}%')
    query += " LIMIT 50"
    
    cur.execute(query, tuple(params))
    activities = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(a) for a in activities])

@app.route('/api/stops/reorder', methods=['POST'])
@login_required
def reorder_stops():
    d = request.json 
    trip_id = d.get('trip_id')
    stop_ids = d.get('stops', [])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if not trip:
        cur.close()
        conn.close()
        return jsonify({'error': 'unauthorized'}), 403
        
    for i, sid in enumerate(stop_ids):
        cur.execute("UPDATE stops SET position=%s WHERE id=%s AND trip_id=%s", (i, sid, trip_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/share/<int:trip_id>/copy', methods=['POST'])
@login_required
def copy_trip(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND is_public=1", (trip_id,))
    src_trip = cur.fetchone()
    if not src_trip:
        cur.close()
        conn.close()
        return redirect(url_for('dashboard'))
    
    uid = session['user_id']
    cur.execute("""INSERT INTO trips (user_id, name, description, start_date, end_date, cover, is_public, total_budget) 
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (uid, src_trip['name'] + ' (Copy)', src_trip['description'], src_trip['start_date'], src_trip['end_date'], src_trip['cover'], 0, src_trip['total_budget']))
    new_tid = cur.fetchone()['id']
    
    cur.execute("SELECT * FROM stops WHERE trip_id=%s", (trip_id,))
    stops = cur.fetchall()
    for s in stops:
        cur.execute("""INSERT INTO stops (trip_id, city, country, start_date, end_date, position) 
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (new_tid, s['city'], s['country'], s['start_date'], s['end_date'], s['position']))
        new_sid = cur.fetchone()['id']
        
        cur.execute("SELECT * FROM activities WHERE stop_id=%s", (s['id'],))
        acts = cur.fetchall()
        for a in acts:
            cur.execute("INSERT INTO activities (stop_id, name, type, cost, duration, description) VALUES (%s,%s,%s,%s,%s,%s)",
                         (new_sid, a['name'], a['type'], a['cost'], a['duration'], a['description']))
                         
    cur.execute("SELECT * FROM budget_items WHERE trip_id=%s", (trip_id,))
    bis = cur.fetchall()
    for b in bis:
        cur.execute("INSERT INTO budget_items (trip_id, category, estimated_cost, actual_cost) VALUES (%s,%s,%s,%s)",
                     (new_tid, b['category'], b['estimated_cost'], b['actual_cost']))
                     
    conn.commit()
    cur.close()
    conn.close()
    flash('Trip copied successfully!')
    return redirect(url_for('itinerary_builder', trip_id=new_tid))

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()
    stats = {}
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    stats['users'] = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE is_admin=1")
    stats['admins'] = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM trips")
    stats['trips'] = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM trips WHERE is_public=1")
    stats['public_trips'] = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM trips WHERE is_public=0")
    stats['private_trips'] = cur.fetchone()['cnt']
    cur.execute("SELECT COALESCE(SUM(total_budget),0) as sm FROM trips")
    stats['budget'] = cur.fetchone()['sm']
    
    cur.execute("SELECT city, COUNT(*) as count FROM stops GROUP BY city ORDER BY count DESC LIMIT 10")
    top_cities = cur.fetchall()
    cur.execute("""
        SELECT id, name, country, region, cost_index, popularity_score, description
        FROM cities
        ORDER BY popularity_score DESC, name ASC
    """)
    popular_destinations = cur.fetchall()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.is_admin, u.created_at,
               COUNT(t.id) AS trip_count,
               COALESCE(SUM(t.total_budget), 0) AS total_budget
        FROM users u
        LEFT JOIN trips t ON t.user_id = u.id
        GROUP BY u.id
        ORDER BY u.id DESC
    """)
    all_users = cur.fetchall()
    cur.execute("""
        SELECT t.id, t.name, t.start_date, t.end_date, t.is_public, t.total_budget, t.created_at,
               u.name AS owner_name, u.email AS owner_email,
               COUNT(s.id) AS stop_count
        FROM trips t
        JOIN users u ON u.id = t.user_id
        LEFT JOIN stops s ON s.trip_id = t.id
        GROUP BY t.id, u.id
        ORDER BY t.created_at DESC
    """)
    all_trips = cur.fetchall()
    cur.close()
    conn.close()
    currency = get_currency_setting()
    return render_template('admin.html', stats=stats, top_cities=top_cities,
                           popular_destinations=popular_destinations,
                           all_users=all_users, all_trips=all_trips,
                           currency=currency, currencies=CURRENCIES)

@app.route('/api/admin/delete_user/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    if uid == session['user_id']:
        return jsonify({'error': 'cannot delete self'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'user not found'}), 404
    delete_user_data(conn, uid)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/admin/user/<int:uid>')
@admin_required
def admin_user_detail(uid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.is_admin, u.created_at,
               (SELECT COUNT(*) FROM trips WHERE user_id = u.id) AS trip_count,
               (SELECT COUNT(*) FROM stops WHERE trip_id IN (SELECT id FROM trips WHERE user_id = u.id)) AS stop_count,
               (SELECT COUNT(*) FROM activities WHERE stop_id IN (
                    SELECT s.id FROM stops s JOIN trips t ON t.id = s.trip_id WHERE t.user_id = u.id
               )) AS activity_count,
               (SELECT COUNT(*) FROM notes WHERE trip_id IN (SELECT id FROM trips WHERE user_id = u.id)) AS note_count,
               COALESCE((SELECT SUM(total_budget) FROM trips WHERE user_id = u.id), 0) AS total_budget
        FROM users u
        WHERE u.id = %s
    """, (uid,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'user not found'}), 404

    cur.execute("""
        SELECT t.id, t.name, t.description, t.start_date, t.end_date, t.is_public,
               t.total_budget, t.created_at,
               COUNT(DISTINCT s.id) AS stop_count,
               COUNT(DISTINCT a.id) AS activity_count,
               COUNT(DISTINCT b.id) AS budget_item_count,
               COALESCE((SELECT SUM(estimated_cost) FROM budget_items WHERE trip_id = t.id), 0) AS estimated_budget,
               COALESCE((SELECT SUM(actual_cost) FROM budget_items WHERE trip_id = t.id), 0) AS actual_budget
        FROM trips t
        LEFT JOIN stops s ON s.trip_id = t.id
        LEFT JOIN activities a ON a.stop_id = s.id
        LEFT JOIN budget_items b ON b.trip_id = t.id
        WHERE t.user_id = %s
        GROUP BY t.id
        ORDER BY t.created_at DESC
    """, (uid,))
    trips = cur.fetchall()

    trip_ids = [t['id'] for t in trips]
    stops_by_trip = {}
    budget_by_trip = {}
    notes_by_trip = {}
    if trip_ids:
        placeholders = ','.join('%s' for _ in trip_ids)
        cur.execute(f"""
            SELECT id, trip_id, city, country, start_date, end_date, position
            FROM stops
            WHERE trip_id IN ({placeholders})
            ORDER BY trip_id, position
        """, tuple(trip_ids))
        stops = cur.fetchall()
        
        cur.execute(f"""
            SELECT id, trip_id, category, estimated_cost, actual_cost
            FROM budget_items
            WHERE trip_id IN ({placeholders})
            ORDER BY trip_id, id
        """, tuple(trip_ids))
        budgets = cur.fetchall()
        
        cur.execute(f"""
            SELECT id, trip_id, content, created_at
            FROM notes
            WHERE trip_id IN ({placeholders})
            ORDER BY created_at DESC
        """, tuple(trip_ids))
        notes = cur.fetchall()
        
        for stop in stops:
            stops_by_trip.setdefault(stop['trip_id'], []).append(dict(stop))
        for budget in budgets:
            budget_by_trip.setdefault(budget['trip_id'], []).append(dict(budget))
        for note in notes:
            notes_by_trip.setdefault(note['trip_id'], []).append(dict(note))

    cur.close()
    conn.close()
    return jsonify({
        'user': dict(user),
        'trips': [
            {
                **dict(trip),
                'stops': stops_by_trip.get(trip['id'], []),
                'budget_items': budget_by_trip.get(trip['id'], []),
                'notes': notes_by_trip.get(trip['id'], []),
            }
            for trip in trips
        ]
    })

@app.route('/api/admin/delete_trip/<int:trip_id>', methods=['DELETE'])
@admin_required
def admin_delete_trip(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM trips WHERE id=%s", (trip_id,))
    trip = cur.fetchone()
    if not trip:
        cur.close()
        conn.close()
        return jsonify({'error': 'trip not found'}), 404
    delete_trip_data(conn, trip_id)
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/admin/toggle_trip_public/<int:trip_id>', methods=['POST'])
@admin_required
def admin_toggle_trip_public(trip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_public FROM trips WHERE id=%s", (trip_id,))
    trip = cur.fetchone()
    if not trip:
        cur.close()
        conn.close()
        return jsonify({'error': 'trip not found'}), 404
    new_state = 0 if trip['is_public'] else 1
    cur.execute("UPDATE trips SET is_public=%s WHERE id=%s", (new_state, trip_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'is_public': bool(new_state)})

@app.route('/api/admin/toggle_user_admin/<int:uid>', methods=['POST'])
@admin_required
def admin_toggle_user_admin(uid):
    if uid == session['user_id']:
        return jsonify({'error': 'cannot change self'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'user not found'}), 404
    new_state = 0 if user['is_admin'] else 1
    cur.execute("UPDATE users SET is_admin=%s WHERE id=%s", (new_state, uid))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'is_admin': bool(new_state)})

@app.route('/api/admin/currency', methods=['POST'])
@admin_required
def admin_update_currency():
    data = request.get_json(silent=True) or {}
    code = data.get('currency', '').strip().upper()
    if not set_currency_setting(code):
        return jsonify({'error': 'unsupported currency'}), 400
    return jsonify({'ok': True, 'currency': get_currency_setting()})

@app.route('/api/admin/destinations', methods=['POST'])
@admin_required
def admin_add_destination():
    data = request.get_json(silent=True) or request.form
    name = data.get('name', '').strip()
    country = data.get('country', '').strip()
    region = data.get('region', '').strip()
    description = data.get('description', '').strip()
    if not name or not country:
        return jsonify({'error': 'name and country are required'}), 400
    try:
        cost_index = max(0, min(100, int(data.get('cost_index') or 50)))
        popularity_score = max(0, min(100, int(data.get('popularity_score') or 50)))
    except ValueError:
        return jsonify({'error': 'cost and popularity must be numbers'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cities (name, country, region, cost_index, popularity_score, description)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (name, country, region, cost_index, popularity_score, description))
    new_id = cur.fetchone()['id']
    conn.commit()
    cur.execute("SELECT * FROM cities WHERE id=%s", (new_id,))
    city = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'destination': dict(city)})

@app.route('/api/admin/destinations/<int:city_id>', methods=['PUT'])
@admin_required
def admin_update_destination(city_id):
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    country = data.get('country', '').strip()
    region = data.get('region', '').strip()
    description = data.get('description', '').strip()
    if not name or not country:
        return jsonify({'error': 'name and country are required'}), 400
    try:
        cost_index = max(0, min(100, int(data.get('cost_index') or 50)))
        popularity_score = max(0, min(100, int(data.get('popularity_score') or 50)))
    except ValueError:
        return jsonify({'error': 'cost and popularity must be numbers'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM cities WHERE id=%s", (city_id,))
    city = cur.fetchone()
    if not city:
        cur.close()
        conn.close()
        return jsonify({'error': 'destination not found'}), 404
    cur.execute("""
        UPDATE cities
        SET name=%s, country=%s, region=%s, cost_index=%s, popularity_score=%s, description=%s
        WHERE id=%s
    """, (name, country, region, cost_index, popularity_score, description, city_id))
    conn.commit()
    cur.execute("SELECT * FROM cities WHERE id=%s", (city_id,))
    updated = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({'ok': True, 'destination': dict(updated)})

@app.route('/api/admin/destinations/<int:city_id>', methods=['DELETE'])
@admin_required
def admin_delete_destination(city_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM cities WHERE id=%s", (city_id,))
    city = cur.fetchone()
    if not city:
        cur.close()
        conn.close()
        return jsonify({'error': 'destination not found'}), 404
    cur.execute("DELETE FROM city_activities WHERE city_id=%s", (city_id,))
    cur.execute("DELETE FROM cities WHERE id=%s", (city_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/profile/delete', methods=['POST'])
@login_required
def delete_profile():
    conn = get_db()
    cur = conn.cursor()
    uid = session['user_id']
    cur.execute("SELECT id FROM trips WHERE user_id=%s", (uid,))
    trips = cur.fetchall()
    for t in trips:
        tid = t['id']
        cur.execute("DELETE FROM activities WHERE stop_id IN (SELECT id FROM stops WHERE trip_id=%s)", (tid,))
        cur.execute("DELETE FROM stops WHERE trip_id=%s", (tid,))
        cur.execute("DELETE FROM checklist WHERE trip_id=%s", (tid,))
        cur.execute("DELETE FROM notes WHERE trip_id=%s", (tid,))
        cur.execute("DELETE FROM budget_items WHERE trip_id=%s", (tid,))
    cur.execute("DELETE FROM trips WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.commit()
    cur.close()
    conn.close()
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/budget_items', methods=['POST'])
@login_required
def add_budget_item():
    d = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (d['trip_id'], session['user_id']))
    trip = cur.fetchone()
    if not trip:
        cur.close()
        conn.close()
        return jsonify({'error': 'unauthorized'}), 403
    
    cur.execute("INSERT INTO budget_items (trip_id, category, estimated_cost) VALUES (%s,%s,%s) RETURNING id",
                       (d['trip_id'], d['category'], float(d.get('estimated_cost',0))))
    bid = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': bid, 'category': d['category'], 'estimated_cost': float(d.get('estimated_cost',0))})

@app.route('/api/budget_items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_budget_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM budget_items WHERE id=%s AND trip_id IN (SELECT id FROM trips WHERE user_id=%s)", (item_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/generate_itinerary', methods=['POST'])
@login_required
def generate_itinerary():
    d = request.json
    trip_id = d.get('trip_id')
    destination = d.get('destination')
    days = int(d.get('days', 3))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return jsonify({'error': 'unauthorized'}), 403
    
    prompt = f"""
    You are a travel planning assistant. Generate a {days}-day itinerary for {destination}.
    Return ONLY a valid JSON object with the following structure, no markdown blocks or extra text:
    {{
      "days": [
        {{
          "day_number": 1,
          "city": "City Name",
          "activities": [
            {{ "name": "Activity Name", "type": "sightseeing|food|adventure|culture|transport", "cost": 50, "duration": "2 hours", "description": "Brief description" }}
          ]
        }}
      ]
    }}
    """
    
    def save_itinerary(data):
        cur.execute("SELECT COUNT(*) as cnt FROM stops WHERE trip_id=%s", (trip_id,))
        pos = cur.fetchone()['cnt']
        for day in data.get('days', []):
            cur.execute("INSERT INTO stops (trip_id, city, country, position) VALUES (%s,%s,%s,%s) RETURNING id",
                                (trip_id, day.get('city', destination), destination, pos))
            sid = cur.fetchone()['id']
            pos += 1
            for act in day.get('activities', []):
                cur.execute("INSERT INTO activities (stop_id, name, type, cost, duration, description) VALUES (%s,%s,%s,%s,%s,%s)",
                                 (sid, act.get('name'), act.get('type', 'sightseeing'), float(act.get('cost', 0)), act.get('duration', ''), act.get('description', '')))
        conn.commit()

    def fallback_itinerary():
        templates = [
            [
                ('Arrival and neighborhood walk', 'sightseeing', 0, '2 hours', 'Arrive, settle in, and explore the nearby area at an easy pace.'),
                ('Local food experience', 'food', 25, '1.5 hours', 'Try a popular local dish or cafe close to your stay.'),
                ('Sunset viewpoint', 'culture', 10, '1 hour', 'End the day at a scenic or culturally important spot.'),
            ],
            [
                ('Historic highlights tour', 'culture', 35, '3 hours', 'Visit the key landmarks, old town areas, museums, or heritage sites.'),
                ('Market or shopping street', 'sightseeing', 15, '2 hours', 'Browse local shops, markets, and everyday city life.'),
                ('Dinner in a popular district', 'food', 35, '2 hours', 'Have dinner in a well-known dining area.'),
            ],
            [
                ('Nature or adventure activity', 'adventure', 45, '3 hours', 'Add an outdoor activity, park, beach, hike, or guided adventure.'),
                ('Relaxed cafe break', 'food', 15, '1 hour', 'Keep the schedule comfortable with a slower mid-day break.'),
                ('Cultural evening', 'culture', 30, '2 hours', 'Watch a show, attend a local event, or explore night markets.'),
            ],
        ]
        days_data = []
        for i in range(max(1, days)):
            activities = templates[i % len(templates)]
            days_data.append({
                'day_number': i + 1,
                'city': destination,
                'activities': [
                    {
                        'name': name,
                        'type': typ,
                        'cost': cost,
                        'duration': duration,
                        'description': description,
                    }
                    for name, typ, cost, duration, description in activities
                ]
            })
        return {'days': days_data}

    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful travel planning assistant that only outputs raw JSON. Do not output markdown backticks."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        save_itinerary(data)
        cur.close()
        conn.close()
        return jsonify({'ok': True, 'source': 'ai'})
    except Exception as e:
        save_itinerary(fallback_itinerary())
        cur.close()
        conn.close()
        return jsonify({'ok': True, 'source': 'fallback', 'message': 'AI connection failed, so a starter itinerary was generated locally.'})

# ─── AI BUDGET SUGGESTIONS ───────────────────────────────────────────────────

@app.route('/api/suggest_budget', methods=['POST'])
@login_required
def suggest_budget():
    d = request.json
    trip_id = d.get('trip_id')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE id=%s AND user_id=%s", (trip_id, session['user_id']))
    trip = cur.fetchone()
    if not trip: cur.close(); conn.close(); return jsonify({'error': 'unauthorized'}), 403
    
    cur.execute("SELECT city, country FROM stops WHERE trip_id=%s", (trip_id,))
    stops = cur.fetchall()
    cur.close()
    conn.close()
    
    cities = ", ".join([f"{s['city']}, {s['country']}" for s in stops]) or trip['name']
    
    def fallback_budget_suggestions():
        return {
            'suggestions': [
                {'category': 'Accommodation', 'estimated_per_day': 80, 'tip': 'Compare hotels and homestays before booking.'},
                {'category': 'Food', 'estimated_per_day': 35, 'tip': 'Mix local restaurants with simple breakfasts or snacks.'},
                {'category': 'Transport', 'estimated_per_day': 25, 'tip': 'Use local transit for city travel and book transfers early.'},
                {'category': 'Activities', 'estimated_per_day': 40, 'tip': 'Prioritize paid attractions and keep free walks in between.'},
                {'category': 'Shopping', 'estimated_per_day': 20, 'tip': 'Set a daily souvenir limit to avoid overspending.'},
                {'category': 'Emergency Fund', 'estimated_per_day': 30, 'tip': 'Keep a buffer for delays, medicine, or last-minute changes.'},
            ],
            'source': 'fallback'
        }

    prompt = f"""You are a travel budget expert. Suggest a realistic budget breakdown (in USD) for a trip to {cities}.
Return ONLY a valid JSON with this structure:
{{"suggestions": [{{"category": "Accommodation", "estimated_per_day": 80, "tip": "Book in advance"}}, ...]}}
Include: Accommodation, Food, Transport, Activities, Shopping, Emergency Fund. Exactly 6 items."""
    try:
        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You only output raw JSON. No markdown."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.4,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content.strip())
        data['source'] = 'ai'
        return jsonify(data)
    except Exception as e:
        return jsonify(fallback_budget_suggestions())

# ─── ACTUAL COST UPDATE ──────────────────────────────────────────────────────

@app.route('/api/budget_items/<int:item_id>/actual', methods=['POST'])
@login_required
def update_actual_cost(item_id):
    d = request.json
    actual = float(d.get('actual_cost', 0))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE budget_items SET actual_cost=%s WHERE id=%s AND trip_id IN (SELECT id FROM trips WHERE user_id=%s)",
                 (actual, item_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5050)