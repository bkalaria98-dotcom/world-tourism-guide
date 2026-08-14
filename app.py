from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import mysql.connector
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
import sqlite3


import os
from flask import Flask, render_template

# ફ્લાસ્કને ચોક્કસપણે કહી દો કે templates ફોલ્ડર ક્યાં છે
template_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, template_folder=template_dir)
#app = Flask(__name__)
app.secret_key = "tourism_secret_key_101"

UPLOAD_FOLDER = 'static/photos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'mov', 'avi', 'mkv'}

def get_db_connection():
    conn = sqlite3.connect('render_tourism.db')
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Visitor Logs Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password TEXT,
            role TEXT DEFAULT 'User',
            mobile TEXT,
            address TEXT,
            dob TEXT
        )
    ''')

    # 3. Categories Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_eng TEXT UNIQUE,
            name_guj TEXT
        )
    ''')

    # 4. Locations Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            village_city TEXT,
            district TEXT,
            state TEXT,
            country TEXT
        )
    ''')

    # 5. Places Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER,
            category_id INTEGER,
            image_path TEXT,
            added_by TEXT,
            is_approved INTEGER DEFAULT 0,
            exact_location TEXT,
            food_stay TEXT,
            transport TEXT,
            FOREIGN KEY(location_id) REFERENCES locations(id),
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
    ''')

    # 6. Place Media Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS place_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id INTEGER,
            file_path TEXT,
            media_type TEXT,
            FOREIGN KEY(place_id) REFERENCES places(id)
        )
    ''')

    # 7. Places Translations Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS places_translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id INTEGER,
            lang TEXT,
            title TEXT,
            description TEXT,
            FOREIGN KEY(place_id) REFERENCES places(id)
        )
    ''')

    conn.commit()
    conn.close()

# એપ્લિકેશન શરૂ થાય ત્યારે બધા ટેબલ બનાવવા માટે
init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

WORLD_COUNTRIES = ["India", "United States", "United Kingdom", "Canada", "Australia"]
INDIA_STATES = ["Gujarat", "Maharashtra", "Rajasthan", "Madhya Pradesh", "Goa"]
GUJARAT_DISTRICTS = ["Ahmedabad", "Baroda", "Surat", "Rajkot", "Bhavnagar", "Kutch", "Junagadh"]

from flask import request

from flask import request

@app.before_request
def log_visitor():
    # જો સ્ટેટિક ફાઇલો કે એસેટ્સ લોડ થતી હોય તો લોગ ન કરો
    if request.path.startswith('/static'):
        return

    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO visitor_logs (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()
    except Exception as e:
        print("Visitor log error:", e)



@app.route('/')
def index():
    country_filter = request.args.get('country', 'All Countries')
    state_filter = request.args.get('state', 'All States')
    district_filter = request.args.get('district', 'All Districts')
    category_filter = request.args.get('category', 'All Categories')
    search_query = request.args.get('q', '').strip()
    
    conn = get_db_connection()
    places_list = []
    categories = []
    pending_count = 0
    guest_count = 0
    member_count = 0
    

    if conn:
        #cursor = conn.cursor(dictionary=True)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM places WHERE is_approved = 0")
        res = cursor.fetchone()
        if res: pending_count = res['count']

        cursor.execute("SELECT COUNT(*) as count FROM visitor_logs WHERE user_id IS NULL")
        res = cursor.fetchone()
        if res: guest_count = res['count']

        cursor.execute("SELECT COUNT(*) as count FROM visitor_logs WHERE user_id IS NOT NULL")
        res = cursor.fetchone()
        if res: member_count = res['count']

        cursor.execute("SELECT name_eng FROM categories")
        categories = [r['name_eng'] for r in cursor.fetchall()]

        # === અહીં દેશો, રાજ્યો અને જિલ્લાઓ ડેટાબેઝમાંથી મેળવવાની લાઈનો ઉમેરો ===
        cursor.execute("SELECT DISTINCT country FROM locations WHERE country IS NOT NULL")
        countries = [r['country'] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT state FROM locations WHERE state IS NOT NULL")
        states = [r['state'] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT district FROM locations WHERE district IS NOT NULL")
        districts = [r['district'] for r in cursor.fetchall()]
        # ====================================================================

        current_lang = session.get('lang', 'en')


        query = """
            SELECT p.id, 
                   COALESCE(pt_lang.title, pt_any.title, 'No Title') as title,
                   COALESCE(pt_lang.description, pt_any.description, 'No description') as description,
                   p.image_path as image_path,
                   l.country, l.state, l.district, l.village_city,
                   c.name_eng as category, p.added_by,
                   p.exact_location, p.food_stay, p.transport
            FROM places p
            LEFT JOIN places_translations pt_lang ON p.id = pt_lang.place_id AND pt_lang.lang = ?
            LEFT JOIN (
                SELECT place_id, MIN(title) as title, MIN(description) as description 
                FROM places_translations 
                GROUP BY place_id
            ) pt_any ON p.id = pt_any.place_id
            LEFT JOIN locations l ON p.location_id = l.id
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.is_approved = 1
        """
        
        params = [current_lang]
        
        if country_filter != 'All Countries':
            query += " AND l.country = ?"
            params.append(country_filter)
        if state_filter != 'All States':
            query += " AND l.state = ?"
            params.append(state_filter)
        if district_filter != 'All Districts':
            query += " AND l.district = ?"
            params.append(district_filter)
        if category_filter != 'All Categories':
            query += " AND c.name_eng = ?"
            params.append(category_filter)
        if search_query:
            query += " AND (pt_lang.title LIKE ? OR pt_default.title LIKE ? OR l.village_city LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
                    
        cursor.execute(query, tuple(params))
        places_list = cursor.fetchall()
        
        for place in places_list:
            cursor.execute("SELECT file_path FROM place_media WHERE place_id = ?", (place['id'],))
            media_rows = cursor.fetchall()
            place['photos'] = [row['file_path'] for row in media_rows]
        
        cursor.close()
        conn.close()

    return render_template('index.html', 
                           places=places_list, 
                           categories=categories,
                           countries=countries,       # આ ઉમેરવાનું ન ભૂલતા
                           states=states,             # આ ઉમેરવાનું ન ભૂલતા
                           districts=districts,       # આ ઉમેરવાનું ન ભૂલતા
                           pending_count=pending_count,
                           guest_count=guest_count,
                           member_count=member_count,
                           sel_country=country_filter,
                           sel_state=state_filter,
                           sel_district=district_filter,
                           sel_category=category_filter,
                           search_query=search_query) 



        
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email').strip()
        password = request.form.get('password').strip()
        
        conn = get_db_connection()
        if conn:
            #cursor = conn.cursor(dictionary=True)
            cursor = conn.cursor()
            if action == 'login':
                cursor.execute("SELECT username, email, role FROM users WHERE email=? AND password=?", (email, password))
                user = cursor.fetchone()
                if user:
                    session['logged_in'] = True
                    session['username'] = user['username']
                    session['email'] = user['email']
                    session['role'] = user['role'].strip().lower()
                    flash(f"Welcome back, {user['username']}!", "success")
                    return redirect(url_for('index'))
                else:
                    flash("Invalid Credentials!", "danger")
            elif action == 'register':
                username = request.form.get('username').strip()
                cursor.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, 'User')", (username, email, password))
                conn.commit()
                flash("Registered! Please Log In.", "success")
            conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged Out!", "info")
    return redirect(url_for('index'))

@app.route('/add_place', methods=['GET', 'POST'])
def add_place():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    categories = []
    if conn:
        #cursor = conn.cursor(dictionary=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name_eng FROM categories")
        categories = [r['name_eng'] for r in cursor.fetchall()]
        conn.close()

    if request.method == 'POST':
        user_name = request.form.get('user_name')
        title = request.form.get('title')
        category = request.form.get('category')
        exact_location = request.form.get('exact_location')
        city = request.form.get('city')
        district = request.form.get('district')
        state = request.form.get('state')
        country = request.form.get('country')
        food_stay = request.form.get('food_stay')
        transport = request.form.get('transport')
        description = request.form.get('description')
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM categories WHERE name_eng = ?", (category,))
            cat_row = cursor.fetchone()
            cat_id = cat_row[0] if cat_row else None
            
            cursor.execute("INSERT INTO locations (village_city, district, state, country) VALUES (?, ?, ?, ?)", (city, district, state, country))
            loc_id = cursor.lastrowid
            
            is_approved = 1 if session.get('role') == 'admin' else 0
            
            cursor.execute("""
                INSERT INTO places (location_id, category_id, image_path, added_by, is_approved, exact_location, food_stay, transport) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (loc_id, cat_id, "", user_name, is_approved, exact_location, food_stay, transport))
            place_id = cursor.lastrowid
            
            files = request.files.getlist('photos')
            first_image_path = ""
            
            for i, file in enumerate(files):
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filename = f"place_{place_id}_{i}_{filename}"
                    file_relative_path = os.path.join('photos', filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    
                    if i == 0:
                        first_image_path = file_relative_path

                    cursor.execute("""
                        INSERT INTO place_media (place_id, file_path, media_type) 
                        VALUES (?, ?, ?)
                    """, (place_id, file_relative_path, 'image'))

            if first_image_path:
                cursor.execute("UPDATE places SET image_path = ? WHERE id = ?", (first_image_path, place_id))

            video_file = request.files.get('video')
            if video_file and video_file.filename != '':
                vid_filename = secure_filename(video_file.filename)
                vid_filename = f"vid_{place_id}_{vid_filename}"
                vid_path = os.path.join('photos', vid_filename)
                video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], vid_filename))
                
                cursor.execute("""
                    INSERT INTO place_media (place_id, file_path, media_type) 
                    VALUES (?, ?, ?)
                """, (place_id, vid_path, 'video'))

            world_languages = {
                'en': 'en',
                'hi': 'hi',
                'gu': 'gu',
                'es': 'es',
                'fr': 'fr',
                'de': 'de',
                'zh-CN': 'zh-CN',
                'ja': 'ja',
                'ar': 'ar',
                'ru': 'ru',
                'mr': 'mr',
                'bn': 'bn',
                'te': 'te',
                'ta': 'ta'
            }

            for lang_name, lang_code in world_languages.items():
                try:
                    trans_title = GoogleTranslator(source='auto', target=lang_code).translate(title)
                    trans_desc = GoogleTranslator(source='auto', target=lang_code).translate(description)
                except Exception as e:
                    print(f"Translation Error for {lang_name}: {e}")
                    trans_title, trans_desc = title, description

                cursor.execute("""
                    INSERT INTO places_translations (place_id, lang, title, description) 
                    VALUES (?, ?, ?, ?)
                """, (place_id, lang_code, trans_title, trans_desc))

            conn.commit()
            conn.close()
            flash("Tourist Destination Saved Successfully with Photos, Video & Multi-language Translations!", "success")
            return redirect(url_for('index'))
    return render_template('add_place.html', categories=categories, countries=WORLD_COUNTRIES, states=INDIA_STATES, districts=GUJARAT_DISTRICTS)


@app.route('/view_place/<int:place_id>')
def view_place(place_id):
    conn = get_db_connection()
    place = None
    if conn:
        #cursor = conn.cursor(dictionary=True)
        cursor = conn.cursor()
        current_lang = session.get('lang', 'en') 

        cursor.execute("""
            SELECT p.id, 
                   COALESCE(pt_lang.title, pt_default.title, 'No Title') as title,
                   COALESCE(pt_lang.description, pt_default.description, 'No information available.') as description,
                   p.image_path, c.name_eng as category, p.is_approved, l.village_city,
                   l.country, l.state, l.district,
                   p.exact_location, p.food_stay, p.transport, p.added_by
            FROM places p
            LEFT JOIN places_translations pt_lang ON p.id = pt_lang.place_id AND pt_lang.lang = ?
            LEFT JOIN places_translations pt_default ON p.id = pt_default.place_id AND pt_default.lang = 'en'
            LEFT JOIN locations l ON p.location_id = l.id
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.id = ?
        """, (current_lang, place_id))
        
        place = cursor.fetchone()
        
        # મલ્ટીપલ ફોટા અને વિડિયો લાવવા માટેનું લૂપ
        if place:
            cursor.execute("SELECT file_path, media_type FROM place_media WHERE place_id = ?", (place_id,))
            media_rows = cursor.fetchall()
            place['photos'] = [row['file_path'] for row in media_rows if row['media_type'] == 'image']
            
            # વિડિયો શોધવા માટે
            video_row = next((row for row in media_rows if row['media_type'] == 'video'), None)
            place['video_path'] = video_row['file_path'] if video_row else None

        cursor.close()
        conn.close()
        
    if not place:
        flash("Place not found!", "danger")
        return redirect(url_for('index'))
        
    return render_template('view_place_details.html', place=place)




@app.route('/edit_place/<int:place_id>', methods=['GET', 'POST'])
def edit_place(place_id):
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    #cursor = conn.cursor(dictionary=True)
    cursor = conn.cursor()
    if request.method == 'POST':
        title = request.form.get('title')
        exact_location = request.form.get('exact_location')
        city = request.form.get('city')
        district = request.form.get('district')
        state = request.form.get('state')
        country = request.form.get('country')
        food_stay = request.form.get('food_stay')
        transport = request.form.get('transport')
        description = request.form.get('description')
        
        files = request.files.getlist('photos')
        
        for i, file in enumerate(files):
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"place_{place_id}_edit_{i}_{filename}"
                file_relative_path = os.path.join('photos', filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                cursor.execute("""
                    INSERT INTO place_media (place_id, file_path, media_type) 
                    VALUES (?, ?, ?)
                """, (place_id, file_relative_path, 'image'))

        single_file = request.files.get('photo')
        if single_file and single_file.filename != '':
            filename = secure_filename(single_file.filename)
            file_relative_path = os.path.join('photos', filename)
            single_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            cursor.execute("UPDATE places SET image_path = ? WHERE id = ?", (file_relative_path, place_id))
            cursor.execute("""
                INSERT INTO place_media (place_id, file_path, media_type) 
                VALUES ?, ?, ?)
            """, (place_id, file_relative_path, 'image'))

        cursor.execute("UPDATE places_translations SET title=?, description=? WHERE place_id=?", (title, description, place_id))
        cursor.execute("""
            UPDATE places p 
            JOIN locations l ON p.location_id = l.id 
            SET p.exact_location=?, p.food_stay=?, p.transport=?, l.village_city=?, l.district=?, l.state=?, l.country=?
            WHERE p.id=?
        """, (exact_location, food_stay, transport, city, district, state, country, place_id))
        
        conn.commit()
        conn.close()
        flash("Record Updated Successfully!", "success")
        return redirect(url_for('index'))
        
    cursor.execute("""
        SELECT p.id, pt.title, pt.description, p.exact_location, p.food_stay, p.transport, p.added_by,
               l.village_city, l.district, l.state, l.country, c.name_eng as category
        FROM places p
        LEFT JOIN places_translations pt ON p.id = pt.place_id
        LEFT JOIN locations l ON p.location_id = l.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.id = ?
    """, (place_id,))
    place = cursor.fetchone()
    
    cursor.execute("SELECT name_eng FROM categories")
    categories = [r['name_eng'] for r in cursor.fetchall()]
    conn.close()
    
    return render_template('edit_place.html', place=place, categories=categories, countries=WORLD_COUNTRIES, states=INDIA_STATES, districts=GUJARAT_DISTRICTS)

@app.route('/admin/approval')
def approval_panel():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    pending_places = []
    if conn:
        #cursor = conn.cursor(dictionary=True)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, COALESCE(pt.title, 'No Title') as title, p.added_by 
            FROM places p 
            LEFT JOIN places_translations pt ON p.id = pt.place_id AND pt.lang = 'en' 
            WHERE p.is_approved = 0
        """)
        pending_places = cursor.fetchall()
        conn.close()
    return render_template('approval.html', pending_places=pending_places)

@app.route('/admin/approve/<int:place_id>', methods=['POST'])
def approve_place(place_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE places SET is_approved = 1 WHERE id = ?", (place_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('approval_panel'))

@app.route('/admin/delete/<int:place_id>', methods=['POST'])
def delete_place(place_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM places WHERE id = ?", (place_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('approval_panel'))

@app.route('/admin/categories')
def admin_categories():
    conn = get_db_connection()
    categories = []
    if conn:
        #cursor = conn.cursor(dictionary=True)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        conn.close()
    return render_template('categories.html', categories=categories)

@app.route('/add_category', methods=['POST'])
def add_category():
    if session.get('role') != 'admin':
        flash("Unauthorized!", "danger")
        return redirect(url_for('index'))
    
    cat_name = request.form.get('category_name').strip()
    conn = get_db_connection()
    if conn and cat_name:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO categories (name_eng, name_guj) VALUES (?, ?)", (cat_name, cat_name))
            conn.commit()
            flash("Category Added Successfully!", "success")
        except Exception as e:
            flash(f"Error: {e}", "danger")
        finally:
            conn.close()
    return redirect(url_for('admin_categories'))

@app.route('/admin/permissions')
def admin_permissions():
    if session.get('role') != 'admin':
        flash("Unauthorized Access!", "danger")
        return redirect(url_for('index'))
    return redirect(url_for('approval_panel'))

@app.route('/admin/delete_category/<int:cat_id>', methods=['POST'])
def delete_category(cat_id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        conn.commit()
        conn.close()
        flash("Category deleted successfully!", "success")
    else:
        flash("Unauthorized!", "danger")
    return redirect(url_for('admin_categories'))

@app.route('/admin/view_place_details/<int:place_id>')
def view_place_details(place_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    #cursor = conn.cursor(dictionary=True)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, pt.title, pt.description, l.village_city, l.district, l.state, l.country, c.name_eng as category
        FROM places p
        LEFT JOIN places_translations pt ON p.id = pt.place_id
        LEFT JOIN locations l ON p.location_id = l.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.id = ?
    """, (place_id,))
    place = cursor.fetchone()
    conn.close()
    
    photos_folder = app.config.get('PHOTOS_FOLDER', 'static/photos')
    return render_template('view_place_details.html', place=place, photos_folder=photos_folder)

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    #cursor = conn.cursor(dictionary=True)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.id, COALESCE(pt.title, 'No Title') as title, p.added_by 
        FROM places p 
        LEFT JOIN places_translations pt ON p.id = pt.place_id 
        WHERE p.is_approved = 0
    """)
    pending_places = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as count FROM visitor_logs WHERE user_id IS NULL")
    guest_data = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(*) as count FROM visitor_logs WHERE user_id IS NOT NULL")
    member_data = cursor.fetchone()
    
    conn.close()
    
    return render_template('admin.html', 
                           pending_places=pending_places, 
                           guest_count=guest_data['count'], 
                           member_count=member_data['count'])

@app.route('/profile')
def user_profile():
    if not session.get('logged_in'):
        flash("Please log in first!", "danger")
        return redirect(url_for('login'))
        
    username = session.get('username')
    user_places = []
    user_data = None
    
    conn1 = get_db_connection()
    if conn1:
        cursor1 = conn1.cursor(dictionary=True)
        cursor1.execute("SELECT * FROM users WHERE username = ?", (username,))
        user_data = cursor1.fetchone()
        cursor1.fetchall()
        cursor1.close()
        conn1.close()

    conn2 = get_db_connection()
    if conn2:
        cursor2 = conn2.cursor(dictionary=True)
        cursor2.execute("""
            SELECT p.id, pt.title, p.image_path, c.name_eng as category, p.is_approved, l.village_city
            FROM places p
            LEFT JOIN places_translations pt ON p.id = pt.place_id
            LEFT JOIN locations l ON p.location_id = l.id
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.added_by = ?
        """, (username,))
        user_places = cursor2.fetchall()
        cursor2.close()
        conn2.close()
        
    return render_template('profile.html', user_places=user_places, user=user_data)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if not session.get('logged_in'):
        flash("Please log in first!", "danger")
        return redirect(url_for('login'))
    
    current_username = session.get('username')
    new_username = request.form.get('username')
    mobile = request.form.get('mobile')
    address = request.form.get('address')
    dob = request.form.get('dob')
    
    if not dob:
        dob = None
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET username = ?, mobile = ?, address = ?, dob = ? 
                WHERE username = ?
            """, (new_username, mobile, address, dob, current_username))
            conn.commit()
            cursor.close()
            conn.close()
            
            session['username'] = new_username
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            print("Error updating profile:", e)
            
    # 🌟 પ્રોફાઇલ અપડેટ થયા પછી સીધા હોમ પેજ (index) પર રીડાયરેક્ટ કરશે
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
