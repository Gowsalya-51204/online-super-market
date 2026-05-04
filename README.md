# Online Super Market - Flask Starter

## Overview
Minimal starter project for an Online Super Market using Python (Flask) and MySQL.
Supports Admin, Seller, and User roles, with:
- Category and Product CRUD (seller/Admin)
- Seller registration/login
- User registration/login, add to cart, place COD orders
- Order view and status update
- Feedback system

## Setup
1. Install Python 3.8+
2. Create MySQL database and run the provided `database.sql`
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Start the app:
   ```
   export FLASK_APP=app.py
   flask run
   ```
   Or on Windows:
   ```
   set FLASK_APP=app.py
   flask run
   ```

MySQL connection is configured in `app.py` with:
- host='localhost', user='root', password='', db='online_supermarket'

Adjust credentials as needed.

