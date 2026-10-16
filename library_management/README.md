# Marginalia - Library Management System

Flask + SQLite web app for running a small library.

## Features
- Admin login (hashed password, session based)
- Dashboard: live stats, newest-books shelf, overdue list, category chart
- Books: add, edit, delete, search by title/author/ISBN, filter by category, live availability
- Members: add, edit, delete, search, books-out count
- Issue & return: choose loan days, automatic due dates, fine of Rs 2/day when late
- Responsive layout with automatic dark mode

## Accounts
- Librarian: admin / admin123 (full management)
- Members: sign in with email + password (demo: aarav@example.com / member123) or register at /register
- Members get their own desk: current loans with progress bars, fines, history, catalogue browsing, profile
- Librarians can set or reset a member's password from Members > Edit

## Run
    python -m venv venv
    source venv/bin/activate        # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000 and sign in with **admin / admin123**.
The database (library.db) and sample data are created on first run.

## Configure (optional environment variables)
SECRET_KEY, LIB_ADMIN, LIB_PASSWORD (applied when the database is first created).
Change FINE_PER_DAY and LOAN_DAYS at the top of app.py.
