import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import pymysql
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# MySQL connection
def get_db():
    conn = pymysql.connect(host='localhost', user='root', password='', db='online_supermarket',
                           cursorclass=pymysql.cursors.DictCursor, autocommit=True)
    return conn

# Home
@app.route('/index')
#@app.route('/')
def index():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT p.*, c.category_name, s.shop_name
                       FROM product p
                       LEFT JOIN category c ON p.category_id=c.category_id
                       LEFT JOIN seller s ON p.seller_id=s.seller_id''')
        products = cur.fetchall()
    return render_template('index.html', products=products)

#
@app.route('/')
def start():
    return render_template('start.html')


# User registration
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        data = {
            'first_name': request.form['first_name'],
            'last_name': request.form['last_name'],
            'dob': request.form['dob'],
            'mobile': request.form['mobile'],
            'address': request.form['address'],
            'email': request.form['email'],
            'password': request.form['password']
        }
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO user_account
                           (first_name,last_name,dob,mobile,address,email,password)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                        (data['first_name'],data['last_name'],data['dob'],data['mobile'],
                         data['address'],data['email'],data['password']))
        flash('Registration successful. Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

# Login (user/seller/admin)
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email')
        password = request.form.get('password')
        conn = get_db()
        with conn.cursor() as cur:
            if role == 'user':
                cur.execute('SELECT * FROM user_account WHERE email=%s AND password=%s', (email, password))
                user = cur.fetchone()
                if user:
                    session['user'] = user
                    return redirect(url_for('user_dashboard'))
                flash('Invalid user credentials')
            elif role == 'seller':
                cur.execute('SELECT * FROM seller WHERE email=%s AND password=%s', (email, password))
                seller = cur.fetchone()
                if seller:
                    session['seller'] = seller
                    return redirect(url_for('seller_dashboard'))
                flash('Invalid seller credentials')
            else:
                cur.execute('SELECT * FROM admin WHERE username=%s AND password=%s', (email, password))
                admin = cur.fetchone()
                if admin:
                    session['admin'] = admin
                    return redirect(url_for('admin_dashboard'))
                flash('Invalid admin credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# User dashboard (cart + quick link to orders)
@app.route('/user')
def user_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT c.*, p.product_name, p.photo, p.price
                       FROM cart c JOIN product p ON c.product_id=p.product_id
                       WHERE c.user_id=%s''', (session['user']['user_id'],))
        cart_items = cur.fetchall()
    return render_template('user_dashboard.html', cart_items=cart_items)

# View Orders (user) with per-item status & feedback link
@app.route('/my_orders')
def my_orders():
    if 'user' not in session:
        return redirect(url_for('login'))
    uid = session['user']['user_id']
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM orders WHERE user_id=%s ORDER BY created_on DESC', (uid,))
        orders = cur.fetchall()
        # Map order_id -> items
        order_items = {}
        for o in orders:
            cur.execute('''SELECT oi.*, p.product_name, p.brand_name, s.shop_name
                           FROM order_items oi
                           JOIN product p ON oi.product_id=p.product_id
                           LEFT JOIN seller s ON oi.seller_id=s.seller_id
                           WHERE oi.order_id=%s''', (o['order_id'],))
            order_items[o['order_id']] = cur.fetchall()
    return render_template('my_orders.html', orders=orders, order_items=order_items)

# Add to cart
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user' not in session:
        flash('Please login to add to cart')
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM cart WHERE user_id=%s AND product_id=%s',
                    (session['user']['user_id'], product_id))
        existing = cur.fetchone()
        if existing:
            cur.execute('UPDATE cart SET qty = qty + 1 WHERE cart_id=%s', (existing['cart_id'],))
        else:
            cur.execute('INSERT INTO cart (user_id, product_id, qty) VALUES (%s,%s,%s)',
                        (session['user']['user_id'], product_id, 1))
    flash('Added to cart')
    return redirect(url_for('index'))

# Place order (COD)
@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user' not in session:
        return redirect(url_for('login'))
    shipping_address = request.form.get('shipping_address')
    phone = request.form.get('phone')
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT c.*, p.price, p.seller_id
                       FROM cart c JOIN product p ON c.product_id=p.product_id
                       WHERE c.user_id=%s''', (session['user']['user_id'],))
        items = cur.fetchall()
        if not items:
            flash('Cart empty')
            return redirect(url_for('user_dashboard'))
        total = sum(item['price'] * item['qty'] for item in items)
        cur.execute('''INSERT INTO orders (user_id,total,shipping_address,phone,status)
                       VALUES (%s,%s,%s,%s,%s)''',
                    (session['user']['user_id'], total, shipping_address, phone, 'Pending'))
        order_id = cur.lastrowid
        for it in items:
            cur.execute('''INSERT INTO order_items (order_id,product_id,seller_id,qty,price,status)
                           VALUES (%s,%s,%s,%s,%s,%s)''',
                        (order_id, it['product_id'], it['seller_id'], it['qty'], it['price'], 'Pending'))
        cur.execute('DELETE FROM cart WHERE user_id=%s', (session['user']['user_id'],))
    flash('Order placed (Cash on Delivery).')
    return redirect(url_for('my_orders'))

# Seller registration
@app.route('/seller/register', methods=['GET','POST'])
def seller_register():
    if request.method == 'POST':
        data = (request.form['username'], request.form['password'], request.form['shop_name'],
                request.form['gst_no'], request.form['shop_address'], request.form['mobile'], request.form['email'])
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO seller
                           (username,password,shop_name,gst_no,shop_address,mobile,email)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)''', data)
        flash('Seller registered, please login.')
        return redirect(url_for('login'))
    return render_template('seller_register.html')

# Seller dashboard (own products, orders with item statuses, feedback)
@app.route('/seller', endpoint='seller_dashboard')
def seller_dashboard():
    if 'seller' not in session:
        return redirect(url_for('login'))
    sid = session['seller']['seller_id']
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM product WHERE seller_id=%s', (sid,))
        products = cur.fetchall()
        # Orders containing this seller's items
        cur.execute('''SELECT o.*
                       FROM orders o
                       JOIN order_items oi ON o.order_id=oi.order_id
                       WHERE oi.seller_id=%s
                       GROUP BY o.order_id
                       ORDER BY o.created_on DESC''', (sid,))
        orders = cur.fetchall()
        # For quick status view per order: items for this seller
        order_items = {}
        for o in orders:
            cur.execute('''SELECT oi.*, p.product_name, u.first_name, u.last_name, o.shipping_address, o.phone
                           FROM order_items oi
                           JOIN product p ON oi.product_id=p.product_id
                           JOIN orders o ON oi.order_id=o.order_id
                           LEFT JOIN user_account u ON o.user_id=u.user_id
                           WHERE oi.order_id=%s AND oi.seller_id=%s''', (o['order_id'], sid))
            order_items[o['order_id']] = cur.fetchall()
        # Seller-specific feedback
        cur.execute('''SELECT f.*, p.product_name, ua.first_name, ua.last_name
                       FROM feedback f
                       LEFT JOIN product p ON f.product_id=p.product_id
                       LEFT JOIN user_account ua ON f.user_id=ua.user_id
                       WHERE f.seller_id=%s
                       ORDER BY f.created_on DESC''', (sid,))
        feedbacks = cur.fetchall()
    return render_template('seller_dashboard.html', products=products, orders=orders,
                           order_items=order_items, feedbacks=feedbacks)
# Seller - list products (your products)
@app.route('/seller/products')
def seller_list_products():
    if 'seller' not in session:
        return redirect(url_for('login'))
    sid = session['seller']['seller_id']
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM product WHERE seller_id=%s ORDER BY product_id DESC', (sid,))
        products = cur.fetchall()
    return render_template('seller_list_products.html', products=products)

# Seller - list orders containing this seller's items
@app.route('/seller/orders')
def seller_list_orders():
    if 'seller' not in session:
        return redirect(url_for('login'))
    sid = session['seller']['seller_id']
    conn = get_db()
    with conn.cursor() as cur:
        # list orders that include items from this seller
        cur.execute('''SELECT DISTINCT o.order_id, o.user_id, o.total, o.shipping_address, o.phone, o.status, o.created_on
                       FROM orders o
                       JOIN order_items oi ON o.order_id=oi.order_id
                       WHERE oi.seller_id=%s
                       ORDER BY o.created_on DESC''', (sid,))
        orders = cur.fetchall()

        # gather items per order for this seller
        order_items = {}
        for o in orders:
            cur.execute('''SELECT oi.*, p.product_name, u.first_name, u.last_name
                           FROM order_items oi
                           JOIN product p ON oi.product_id=p.product_id
                           LEFT JOIN orders ord ON oi.order_id = ord.order_id
                           LEFT JOIN user_account u ON ord.user_id=u.user_id
                           WHERE oi.order_id=%s AND oi.seller_id=%s''', (o['order_id'], sid))
            order_items[o['order_id']] = cur.fetchall()
    return render_template('seller_list_orders.html', orders=orders, order_items=order_items)

# Seller - list feedbacks for this seller's products
@app.route('/seller/feedbacks')
def seller_list_feedbacks():
    if 'seller' not in session:
        return redirect(url_for('login'))
    sid = session['seller']['seller_id']
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT f.*, p.product_name, u.first_name, u.last_name
                       FROM feedback f
                       LEFT JOIN product p ON f.product_id=p.product_id
                       LEFT JOIN user_account u ON f.user_id=u.user_id
                       WHERE f.seller_id=%s
                       ORDER BY f.created_on DESC''', (sid,))
        feedbacks = cur.fetchall()
    return render_template('seller_list_feedbacks.html', feedbacks=feedbacks)

@app.route('/seller/update_item_status/<int:oi_id>', methods=['POST'])
def update_item_status(oi_id):
    if 'seller' not in session:
        return redirect(url_for('login'))
    new_status = request.form.get('status')
    sid = session['seller']['seller_id']
    conn = get_db()
    with conn.cursor() as cur:
        # Update the item (only if it belongs to this seller)
        cur.execute('UPDATE order_items SET status=%s WHERE id=%s AND seller_id=%s',
                    (new_status, oi_id, sid))

        # Fetch the order_id for this item
        cur.execute('SELECT order_id FROM order_items WHERE id=%s', (oi_id,))
        row = cur.fetchone()
        if not row:
            flash('Order item not found.')
            return redirect(url_for('seller_dashboard'))
        order_id = row['order_id']

        # Now examine all items of this order to determine overall order status
        cur.execute('SELECT status, COUNT(*) AS cnt FROM order_items WHERE order_id=%s GROUP BY status', (order_id,))
        status_counts = cur.fetchall()
        # Build a small dict status -> count
        sc = {r['status']: r['cnt'] for r in status_counts}

        # Decide overall order status
        # If every item is Delivered -> Delivered
        # Else if at least one Delivered and at least one not Delivered -> Partially Delivered
        # Else if any item is Shipped/Out for Delivery -> In Transit
        # Else if all Cancelled -> Cancelled
        overall_status = None
        total_items = sum(sc.values())
        delivered_count = sc.get('Delivered', 0)
        cancelled_count = sc.get('Cancelled', 0)
        in_transit_states = ['Shipped', 'Out for Delivery', 'Packed']
        in_transit_count = sum(sc.get(s, 0) for s in in_transit_states)

        if delivered_count == total_items and total_items > 0:
            overall_status = 'Delivered'
        elif cancelled_count == total_items and total_items > 0:
            overall_status = 'Cancelled'
        elif delivered_count > 0 and delivered_count < total_items:
            overall_status = 'Partially Delivered'
        elif in_transit_count > 0:
            overall_status = 'In Transit'
        else:
            # default fallback - keep Pending
            overall_status = 'Pending'

        # Update orders table
        cur.execute('UPDATE orders SET status=%s WHERE order_id=%s', (overall_status, order_id))

    flash(f'Item status updated to {new_status}. Order status: {overall_status}')
    return redirect(url_for('seller_dashboard'))


# Product CRUD (Seller)
@app.route('/product/add', methods=['GET','POST'])
def add_product():
    if 'seller' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM category')
        cats = cur.fetchall()
    if request.method == 'POST':
        f = request.files.get('photo')
        filename = ''
        if f and f.filename:
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        data = (session['seller']['seller_id'], request.form['category_id'], request.form['product_name'],
                request.form['brand_name'], filename, request.form['price'], request.form['warranty'])
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO product
                           (seller_id,category_id,product_name,brand_name,photo,price,warranty)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)''', data)
        flash('Product added')
        return redirect(url_for('seller_dashboard'))
    return render_template('add_product.html', cats=cats)

@app.route('/product/edit/<int:pid>', methods=['GET','POST'])
def edit_product(pid):
    if 'seller' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM product WHERE product_id=%s AND seller_id=%s', (pid, session['seller']['seller_id']))
        product = cur.fetchone()
        cur.execute('SELECT * FROM category')
        cats = cur.fetchall()
    if not product:
        flash('Product not found')
        return redirect(url_for('seller_dashboard'))
    if request.method == 'POST':
        f = request.files.get('photo')
        filename = product['photo']
        if f and f.filename:
            filename = secure_filename(f.filename)
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute('''UPDATE product SET category_id=%s,product_name=%s,brand_name=%s,
                           photo=%s,price=%s,warranty=%s WHERE product_id=%s AND seller_id=%s''',
                        (request.form['category_id'], request.form['product_name'], request.form['brand_name'],
                         filename, request.form['price'], request.form['warranty'], pid, session['seller']['seller_id']))
        flash('Product updated')
        return redirect(url_for('seller_dashboard'))
    return render_template('edit_product.html', product=product, cats=cats)

@app.route('/product/delete/<int:pid>')
def delete_product(pid):
    if 'seller' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM product WHERE product_id=%s AND seller_id=%s',
                    (pid, session['seller']['seller_id']))
    flash('Product deleted')
    return redirect(url_for('seller_dashboard'))
@app.route('/my_feedbacks')
def my_feedbacks():
    if 'user' not in session:
        return redirect(url_for('login'))
    uid = session['user']['user_id']
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT f.*, p.product_name, s.shop_name
                       FROM feedback f
                       LEFT JOIN product p ON f.product_id=p.product_id
                       LEFT JOIN seller s ON f.seller_id=s.seller_id
                       WHERE f.user_id=%s ORDER BY f.created_on DESC''', (uid,))
        feedbacks = cur.fetchall()
    return render_template('my_feedbacks.html', feedbacks=feedbacks)

# Admin dashboard + removals + view feedback
@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM seller')
        sellers = cur.fetchall()
        cur.execute('SELECT * FROM user_account')
        users = cur.fetchall()
        cur.execute('''SELECT p.*, c.category_name, s.shop_name
                       FROM product p
                       LEFT JOIN category c ON p.category_id=c.category_id
                       LEFT JOIN seller s ON p.seller_id=s.seller_id''')
        products = cur.fetchall()
        cur.execute('''SELECT f.*, u.first_name, p.product_name, s.shop_name
                       FROM feedback f
                       LEFT JOIN user_account u ON f.user_id=u.user_id
                       LEFT JOIN product p ON f.product_id=p.product_id
                       LEFT JOIN seller s ON f.seller_id=s.seller_id
                       ORDER BY f.created_on DESC''')
        feedbacks = cur.fetchall()
    return render_template('admin_dashboard.html', sellers=sellers, users=users, products=products, feedbacks=feedbacks)
# Admin - list sellers (summary)
@app.route('/admin/sellers')
def admin_list_sellers():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT seller_id, username, shop_name, email, mobile FROM seller ORDER BY seller_id DESC')
        sellers = cur.fetchall()
    return render_template('admin_list_sellers.html', sellers=sellers)

# Admin - list products
@app.route('/admin/products')
def admin_list_products():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT p.product_id, p.product_name, p.price, s.shop_name FROM product p LEFT JOIN seller s ON p.seller_id=s.seller_id ORDER BY p.product_id DESC')
        products = cur.fetchall()
    return render_template('admin_list_products.html', products=products)

# Admin - list users
@app.route('/admin/users')
def admin_list_users():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT user_id, first_name, last_name, email, mobile FROM user_account ORDER BY user_id DESC')
        users = cur.fetchall()
    return render_template('admin_list_users.html', users=users)

# Admin - list feedbacks
@app.route('/admin/feedbacks')
def admin_list_feedbacks():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''SELECT f.feedback_id, f.created_on, u.first_name, u.last_name, p.product_name, s.shop_name, f.rating
                       FROM feedback f
                       LEFT JOIN user_account u ON f.user_id=u.user_id
                       LEFT JOIN product p ON f.product_id=p.product_id
                       LEFT JOIN seller s ON f.seller_id=s.seller_id
                       ORDER BY f.created_on DESC''')
        feedbacks = cur.fetchall()
    return render_template('admin_list_feedbacks.html', feedbacks=feedbacks)

# Admin - view seller details
@app.route('/admin/view/seller/<int:sid>')
def admin_view_seller(sid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM seller WHERE seller_id=%s', (sid,))
        seller = cur.fetchone()

        # ✅ Add this block here
        if not seller:
            flash('Seller not found')
            return redirect(url_for('admin_list_sellers'))

        # continue only if seller exists
        cur.execute('SELECT * FROM product WHERE seller_id=%s', (sid,))
        products = cur.fetchall()
        cur.execute('SELECT f.*, u.first_name, u.last_name, p.product_name \
                     FROM feedback f \
                     LEFT JOIN user_account u ON f.user_id=u.user_id \
                     LEFT JOIN product p ON f.product_id=p.product_id \
                     WHERE f.seller_id=%s ORDER BY f.created_on DESC', (sid,))
        feedbacks = cur.fetchall()
    return render_template('admin_view_seller.html',
                           seller=seller,
                           products=products,
                           feedbacks=feedbacks)



# Admin - view user details
@app.route('/admin/view/user/<int:uid>')
def admin_view_user(uid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM user_account WHERE user_id=%s', (uid,))
        user = cur.fetchone()
        cur.execute('SELECT * FROM orders WHERE user_id=%s ORDER BY created_on DESC', (uid,))
        orders = cur.fetchall()
    return render_template('admin_view_user.html', user=user, orders=orders)

# Admin - view product details
@app.route('/admin/view/product/<int:pid>')
def admin_view_product(pid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''
            SELECT p.*, c.category_name, s.shop_name
            FROM product p
            LEFT JOIN category c ON p.category_id=c.category_id
            LEFT JOIN seller s ON p.seller_id=s.seller_id
            WHERE p.product_id=%s
        ''', (pid,))
        product = cur.fetchone()
        cur.execute('''
            SELECT f.*, u.first_name, u.last_name
            FROM feedback f
            LEFT JOIN user_account u ON f.user_id=u.user_id
            WHERE f.product_id=%s
            ORDER BY f.created_on DESC
        ''', (pid,))
        feedbacks = cur.fetchall()
    return render_template('admin_view_product.html', product=product, feedbacks=feedbacks)

# Admin - view single feedback
@app.route('/admin/view/feedback/<int:fid>')
def admin_view_feedback(fid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''
            SELECT f.*, u.first_name, u.last_name, p.product_name, s.shop_name
            FROM feedback f
            LEFT JOIN user_account u ON f.user_id=u.user_id
            LEFT JOIN product p ON f.product_id=p.product_id
            LEFT JOIN seller s ON f.seller_id=s.seller_id
            WHERE f.feedback_id=%s
        ''', (fid,))
        fb = cur.fetchone()
    return render_template('admin_view_feedback.html', fb=fb)

@app.route('/admin/remove/seller/<int:sid>')
def remove_seller(sid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM seller WHERE seller_id=%s', (sid,))
    flash('Seller removed')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/remove/user/<int:uid>')
def remove_user(uid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM user_account WHERE user_id=%s', (uid,))
    flash('User removed')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/remove/product/<int:pid>')
def remove_product(pid):
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM product WHERE product_id=%s', (pid,))
    flash('Product removed')
    return redirect(url_for('admin_dashboard'))

# Feedback routes
@app.route('/feedback/<int:product_id>', methods=['GET','POST'])
def feedback(product_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    # Optional rule: allow feedback only if delivered
    uid = session['user']['user_id']
    conn = get_db()
    if request.method == 'POST':
        comment = request.form['comment']
        rating = int(request.form.get('rating', 5))
        with conn.cursor() as cur:
            cur.execute('SELECT seller_id FROM product WHERE product_id=%s', (product_id,))
            prod = cur.fetchone()
            seller_id = prod['seller_id'] if prod else None
            cur.execute('''INSERT INTO feedback (user_id,product_id,seller_id,comment,rating)
                           VALUES (%s,%s,%s,%s,%s)''', (uid, product_id, seller_id, comment, rating))
        flash('Feedback submitted')
        return redirect(url_for('my_orders'))
    # show product name
    with conn.cursor() as cur:
        cur.execute('SELECT product_name FROM product WHERE product_id=%s', (product_id,))
        prod = cur.fetchone()
    return render_template('feedback.html', product_id=product_id, product_name=(prod['product_name'] if prod else 'Product'))
# @app.route('/user/cart')
# def user_cart():
#     if 'user' not in session:
#         flash('Please login to view cart')
#         return redirect(url_for('login'))
#
#     uid = session['user']['user_id']
#     conn = get_db()
#     with conn.cursor() as cur:
#         cur.execute('''
#             SELECT c.*, p.product_name, p.photo, p.price
#             FROM cart c
#             JOIN product p ON c.product_id = p.product_id
#             WHERE c.user_id = %s
#         ''', (uid,))
#         cart_items = cur.fetchall()
#
#     return render_template('user_cart.html', cart_items=cart_items)
@app.route('/user/cart')
def user_cart():
    if 'user' not in session:
        flash('Please login to view cart')
        return redirect(url_for('login'))

    uid = session['user']['user_id']
    conn = get_db()

    # Query cart rows joined with product info
    query = """
        SELECT c.*, p.product_name, p.photo, p.price
        FROM cart c
        JOIN product p ON c.product_id = p.product_id
        WHERE c.user_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (uid,))
        rows = cur.fetchall()

        # Convert to list of dicts (works whether cursor returns tuples or dicts)
        if rows and isinstance(rows[0], dict):
            cart_items = rows
        else:
            cols = [d[0] for d in cur.description]
            cart_items = [dict(zip(cols, r)) for r in rows]

    # Normalize quantity field name and compute subtotal + total
    total = 0.0
    for item in cart_items:
        # Try common qty field names; fallback to 0
        qty = item.get('qty')
        if qty is None:
            qty = item.get('quantity')
        if qty is None:
            qty = item.get('cart_qty')
        try:
            qty = int(qty or 0)
        except (ValueError, TypeError):
            qty = 0

        # Price -> float
        try:
            price = float(item.get('price') or 0)
        except (ValueError, TypeError):
            # If price contains currency chars, strip non-numeric (basic)
            import re
            raw = str(item.get('price') or '0')
            num = re.sub(r'[^\d\.\-]', '', raw)
            try:
                price = float(num or 0)
            except:
                price = 0.0

        subtotal = price * qty
        item['qty'] = qty           # normalize to 'qty' for template
        item['price'] = price       # ensure numeric
        item['subtotal'] = subtotal # precomputed subtotal
        total += subtotal

    return render_template('user_cart.html', cart_items=cart_items, total=total)

@app.route('/cart/delete/<int:cid>')
def delete_cart_item(cid):
    if 'user' not in session:
        return redirect(url_for('login'))
    uid = session['user']['user_id']
    conn = get_db()
    with conn.cursor() as cur:
        # Delete only if the item belongs to the logged-in user
        cur.execute('DELETE FROM cart WHERE cart_id=%s AND user_id=%s', (cid, uid))
    flash('Item removed from cart')
    return redirect(url_for('user_cart'))

# Serve uploads
@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__=='__main__':
    app.run(debug=True)
