"""Marginalia - Library Management System (Flask + SQLite)."""
import os
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, g, redirect, render_template, request, session,
                   url_for, flash)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")
LOAN_DAYS = 14        # default loan period
FINE_PER_DAY = 2      # fine in ₹ per overdue day
ADMIN_USER = os.environ.get("LIB_ADMIN", "Shrikant")
ADMIN_PASS = os.environ.get("LIB_PASSWORD", "12345")

SCHEMA = """
CREATE TABLE IF NOT EXISTS books(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, author TEXT NOT NULL,
  isbn TEXT, category TEXT DEFAULT 'General', copies INTEGER DEFAULT 1, added TEXT);
CREATE TABLE IF NOT EXISTS members(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT,
  phone TEXT, joined TEXT, password TEXT);
CREATE TABLE IF NOT EXISTS issues(
  id INTEGER PRIMARY KEY AUTOINCREMENT, book_id INTEGER NOT NULL, member_id INTEGER NOT NULL,
  issued TEXT NOT NULL, due TEXT NOT NULL, returned TEXT, fine INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS admin(username TEXT PRIMARY KEY, password TEXT);
"""


# ---------- database helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def q(sql, args=(), one=False):
    cur = db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    conn = db()
    conn.execute(sql, args)
    conn.commit()


def init_db():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    if "password" not in [r[1] for r in conn.execute("PRAGMA table_info(members)")]:
        conn.execute("ALTER TABLE members ADD COLUMN password TEXT")
    today = date.today()
    if not conn.execute("SELECT 1 FROM admin").fetchone():
        conn.execute("INSERT INTO admin VALUES(?,?)",
                     (ADMIN_USER, generate_password_hash(ADMIN_PASS)))
    if not conn.execute("SELECT 1 FROM books").fetchone():
        books = [
            ("The God of Small Things", "Arundhati Roy", "9780006550686", "Fiction", 3),
            ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", "Biography", 4),
            ("Sapiens", "Yuval Noah Harari", "9780099590088", "History", 2),
            ("Clean Code", "Robert C. Martin", "9780132350884", "Technology", 2),
            ("A Brief History of Time", "Stephen Hawking", "9780553380163", "Science", 2),
            ("The Palace of Illusions", "Chitra Banerjee Divakaruni", "9780385515993", "Fiction", 2),
            ("Atomic Habits", "James Clear", "9780735211292", "Self-help", 5),
            ("Introduction to Algorithms", "Thomas H. Cormen", "9780262033848", "Technology", 1),
            ("Discovery of India", "Jawaharlal Nehru", "9780143031031", "History", 2),
            ("The Alchemist", "Paulo Coelho", "9780061122415", "Fiction", 3),
        ]
        conn.executemany("INSERT INTO books(title,author,isbn,category,copies,added) VALUES(?,?,?,?,?,?)",
                         [b + (today.isoformat(),) for b in books])
        members = [("Aarav Kulkarni", "aarav@example.com", "9876500011"),
                   ("Isha Deshmukh", "isha@example.com", "9876500022"),
                   ("Rohan Patil", "rohan@example.com", "9876500033"),
                   ("Meera Joshi", "meera@example.com", "9876500044")]
        demo_pw = generate_password_hash("member123")
        conn.executemany("INSERT INTO members(name,email,phone,joined,password) VALUES(?,?,?,?,?)",
                         [m + (today.isoformat(), demo_pw) for m in members])
        d = lambda n: (today + timedelta(days=n)).isoformat()
        conn.executemany("INSERT INTO issues(book_id,member_id,issued,due) VALUES(?,?,?,?)",
                         [(1, 1, d(-20), d(-6)), (4, 2, d(-5), d(9)), (7, 3, d(-2), d(12))])
    conn.commit()
    conn.close()


# ---------- template helpers ----------
@app.template_filter("hue")
def hue(text):
    return sum(ord(c) * (i + 3) for i, c in enumerate(text)) % 360


@app.template_filter("pretty")
def pretty(iso):
    return date.fromisoformat(iso).strftime("%d %b %Y") if iso else "-"


@app.context_processor
def inject():
    return {"today": date.today().isoformat(), "FINE": FINE_PER_DAY}


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    """Librarian-only pages. Members are sent to their own desk."""
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            return redirect(url_for("me"))
        return f(*a, **kw)
    return wrapper


def member_required(f):
    """Member-only pages. Librarians are sent to the admin dashboard."""
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login"))
        if session.get("role") != "member":
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return wrapper


def late_fine(due, returned=None):
    end = date.fromisoformat(returned) if returned else date.today()
    return max((end - date.fromisoformat(due)).days, 0) * FINE_PER_DAY


BOOK_SQL = """SELECT b.*, b.copies - (SELECT COUNT(*) FROM issues i
              WHERE i.book_id=b.id AND i.returned IS NULL) AS avail FROM books b"""


# ---------- auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard" if session.get("role") == "admin" else "me"))
    if request.method == "POST":
        ident, pw = request.form["username"].strip(), request.form["password"]
        row = q("SELECT * FROM admin WHERE username=?", (ident,), one=True)
        if row and check_password_hash(row["password"], pw):
            session.clear()
            session.update(user=row["username"], role="admin")
            return redirect(request.args.get("next") or url_for("dashboard"))
        m = q("SELECT * FROM members WHERE lower(email)=lower(?)", (ident,), one=True)
        if m and m["password"] and check_password_hash(m["password"], pw):
            session.clear()
            session.update(user=m["name"], role="member", mid=m["id"])
            return redirect(url_for("me"))
        flash("Wrong email/username or password. Check both and try again.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, email, phone, pw = f["name"].strip(), f["email"].strip(), f["phone"].strip(), f["password"]
        if not (name and email and len(pw) >= 6):
            flash("Enter your name, email and a password of at least 6 characters.", "error")
        elif q("SELECT 1 FROM members WHERE lower(email)=lower(?)", (email,), one=True):
            flash("That email already has an account. Sign in instead.", "error")
        else:
            run("INSERT INTO members(name,email,phone,joined,password) VALUES(?,?,?,?,?)",
                (name, email, phone, date.today().isoformat(), generate_password_hash(pw)))
            mid = q("SELECT id FROM members WHERE lower(email)=lower(?)", (email,), one=True)["id"]
            session.clear()
            session.update(user=name, role="member", mid=mid)
            flash(f"Welcome, {name}. Your library account is ready.", "ok")
            return redirect(url_for("me"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/")
@admin_required
def dashboard():
    t = date.today().isoformat()
    stats = {
        "titles": q("SELECT COUNT(*) c FROM books", one=True)["c"],
        "copies": q("SELECT COALESCE(SUM(copies),0) c FROM books", one=True)["c"],
        "members": q("SELECT COUNT(*) c FROM members", one=True)["c"],
        "out": q("SELECT COUNT(*) c FROM issues WHERE returned IS NULL", one=True)["c"],
        "overdue": q("SELECT COUNT(*) c FROM issues WHERE returned IS NULL AND due<?", (t,), one=True)["c"],
    }
    shelf = q("SELECT * FROM books ORDER BY id DESC LIMIT 14")
    overdue = q("""SELECT i.*, b.title, m.name FROM issues i JOIN books b ON b.id=i.book_id
                   JOIN members m ON m.id=i.member_id WHERE i.returned IS NULL AND i.due<? ORDER BY i.due""", (t,))
    recent = q("""SELECT i.*, b.title, m.name FROM issues i JOIN books b ON b.id=i.book_id
                  JOIN members m ON m.id=i.member_id ORDER BY i.id DESC LIMIT 6""")
    cats = q("SELECT category, SUM(copies) n FROM books GROUP BY category ORDER BY n DESC")
    return render_template("dashboard.html", s=stats, shelf=shelf, overdue=overdue,
                           recent=recent, cats=cats, late_fine=late_fine)


# ---------- books ----------
BOOK_FIELDS = [("title", "Title", "text"), ("author", "Author", "text"), ("isbn", "ISBN", "text"),
               ("category", "Category", "text"), ("copies", "Copies owned", "number")]


@app.route("/books")
@admin_required
def books():
    term, cat = request.args.get("q", "").strip(), request.args.get("cat", "")
    sql, args = BOOK_SQL + " WHERE (b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)", [f"%{term}%"] * 3
    if cat:
        sql += " AND b.category=?"
        args.append(cat)
    rows = q(sql + " ORDER BY b.title", args)
    cats = [r["category"] for r in q("SELECT DISTINCT category FROM books ORDER BY category")]
    return render_template("books.html", books=rows, cats=cats, term=term, cat=cat)


def book_form(book=None):
    if request.method == "POST":
        f = request.form
        vals = (f["title"].strip(), f["author"].strip(), f["isbn"].strip(),
                f["category"].strip() or "General", max(int(f["copies"] or 1), 1))
        if not vals[0] or not vals[1]:
            flash("Title and author are required.", "error")
        elif book:
            run("UPDATE books SET title=?,author=?,isbn=?,category=?,copies=? WHERE id=?", vals + (book["id"],))
            flash(f"Saved changes to “{vals[0]}”.", "ok")
            return redirect(url_for("books"))
        else:
            run("INSERT INTO books(title,author,isbn,category,copies,added) VALUES(?,?,?,?,?,?)",
                vals + (date.today().isoformat(),))
            flash(f"Added “{vals[0]}” to the catalogue.", "ok")
            return redirect(url_for("books"))
    return render_template("form.html", title="Edit book" if book else "Add a book",
                           fields=BOOK_FIELDS, v=(book or request.form or {"copies": 1}),
                           back=url_for("books"))


@app.route("/books/new", methods=["GET", "POST"])
@admin_required
def book_new():
    return book_form()


@app.route("/books/<int:bid>/edit", methods=["GET", "POST"])
@admin_required
def book_edit(bid):
    book = q("SELECT * FROM books WHERE id=?", (bid,), one=True)
    return book_form(book) if book else redirect(url_for("books"))


@app.route("/books/<int:bid>/delete", methods=["POST"])
@admin_required
def book_delete(bid):
    if q("SELECT 1 FROM issues WHERE book_id=? AND returned IS NULL", (bid,), one=True):
        flash("This book is currently issued. Return it before deleting.", "error")
    else:
        run("DELETE FROM books WHERE id=?", (bid,))
        flash("Book deleted.", "ok")
    return redirect(url_for("books"))


# ---------- members ----------
MEMBER_FIELDS = [("name", "Full name", "text"), ("email", "Email (their login)", "email"), ("phone", "Phone", "text"),
                 ("password", "Login password (blank keeps current)", "password")]


@app.route("/members")
@admin_required
def members():
    term = request.args.get("q", "").strip()
    rows = q("""SELECT m.*, (SELECT COUNT(*) FROM issues i WHERE i.member_id=m.id AND i.returned IS NULL) AS out
                FROM members m WHERE m.name LIKE ? OR m.email LIKE ? ORDER BY m.name""", (f"%{term}%",) * 2)
    return render_template("members.html", members=rows, term=term)


def member_form(m=None):
    if request.method == "POST":
        f = request.form
        name, email, phone, pw = (f["name"].strip(), f["email"].strip(), f["phone"].strip(),
                                  f.get("password", "").strip())
        if not name:
            flash("Name is required.", "error")
        elif email and q("SELECT 1 FROM members WHERE lower(email)=lower(?) AND id!=?",
                         (email, m["id"] if m else 0), one=True):
            flash("That email is already registered to another member.", "error")
        elif m:
            run("UPDATE members SET name=?,email=?,phone=? WHERE id=?", (name, email, phone, m["id"]))
            if pw:
                run("UPDATE members SET password=? WHERE id=?", (generate_password_hash(pw), m["id"]))
            flash("Member updated.", "ok")
            return redirect(url_for("members"))
        else:
            run("INSERT INTO members(name,email,phone,joined,password) VALUES(?,?,?,?,?)",
                (name, email, phone, date.today().isoformat(), generate_password_hash(pw or "welcome123")))
            flash(f"Added {name}. Their password is {'the one you set' if pw else 'welcome123'}.", "ok")
            return redirect(url_for("members"))
    return render_template("form.html", title="Edit member" if m else "Add a member",
                           fields=MEMBER_FIELDS, v=(m or request.form or {}), back=url_for("members"))


@app.route("/members/new", methods=["GET", "POST"])
@admin_required
def member_new():
    return member_form()


@app.route("/members/<int:mid>/edit", methods=["GET", "POST"])
@admin_required
def member_edit(mid):
    m = q("SELECT * FROM members WHERE id=?", (mid,), one=True)
    return member_form(m) if m else redirect(url_for("members"))


@app.route("/members/<int:mid>/delete", methods=["POST"])
@admin_required
def member_delete(mid):
    if q("SELECT 1 FROM issues WHERE member_id=? AND returned IS NULL", (mid,), one=True):
        flash("This member still has books out. Return them first.", "error")
    else:
        run("DELETE FROM members WHERE id=?", (mid,))
        flash("Member deleted.", "ok")
    return redirect(url_for("members"))


# ---------- issue & return ----------
@app.route("/issues", methods=["GET", "POST"])
@admin_required
def issues():
    if request.method == "POST":
        bid, mid = int(request.form["book_id"]), int(request.form["member_id"])
        days = max(int(request.form.get("days") or LOAN_DAYS), 1)
        book = q(BOOK_SQL + " WHERE b.id=?", (bid,), one=True)
        if not book or book["avail"] < 1:
            flash("No copies of that book are available right now.", "error")
        else:
            run("INSERT INTO issues(book_id,member_id,issued,due) VALUES(?,?,?,?)",
                (bid, mid, date.today().isoformat(), (date.today() + timedelta(days=days)).isoformat()))
            flash(f"Issued “{book['title']}” for {days} days.", "ok")
        return redirect(url_for("issues"))
    status = request.args.get("s", "active")
    where = {"active": "i.returned IS NULL", "overdue": "i.returned IS NULL AND i.due < date('now','localtime')",
             "returned": "i.returned IS NOT NULL", "all": "1=1"}.get(status, "1=1")
    rows = q(f"""SELECT i.*, b.title, b.author, m.name FROM issues i JOIN books b ON b.id=i.book_id
                 JOIN members m ON m.id=i.member_id WHERE {where} ORDER BY i.id DESC""")
    avail = [b for b in q(BOOK_SQL + " ORDER BY b.title") if b["avail"] > 0]
    return render_template("issues.html", rows=rows, status=status, avail=avail,
                           members=q("SELECT * FROM members ORDER BY name"), late_fine=late_fine, loan=LOAN_DAYS)


@app.route("/issues/<int:iid>/return", methods=["POST"])
@admin_required
def issue_return(iid):
    row = q("SELECT * FROM issues WHERE id=? AND returned IS NULL", (iid,), one=True)
    if row:
        fine = late_fine(row["due"])
        run("UPDATE issues SET returned=?, fine=? WHERE id=?", (date.today().isoformat(), fine, iid))
        flash(f"Book returned. Fine collected: ₹{fine}." if fine else "Book returned on time.", "ok")
    return redirect(url_for("issues"))


# ---------- member area ----------
@app.route("/me")
@member_required
def me():
    mid, t = session["mid"], date.today()
    m = q("SELECT * FROM members WHERE id=?", (mid,), one=True)
    if not m:
        session.clear()
        return redirect(url_for("login"))
    rows = q("""SELECT i.*, b.title, b.author FROM issues i JOIN books b ON b.id=i.book_id
                WHERE i.member_id=? ORDER BY i.due""", (mid,))
    active, history, owed, paid = [], [], 0, 0
    for r in rows:
        if r["returned"]:
            history.append(r)
            paid += r["fine"] or 0
        else:
            iss, due = date.fromisoformat(r["issued"]), date.fromisoformat(r["due"])
            total, used = max((due - iss).days, 1), (t - iss).days
            fine = late_fine(r["due"])
            owed += fine
            active.append(dict(r, left=(due - t).days, pct=max(4, min(100, round(used / total * 100))), fine=fine))
    history.sort(key=lambda r: r["returned"], reverse=True)
    return render_template("member_home.html", m=m, active=active, history=history, owed=owed, paid=paid)


@app.route("/catalogue")
@member_required
def catalogue():
    term, cat = request.args.get("q", "").strip(), request.args.get("cat", "")
    sql = BOOK_SQL.replace("AS avail FROM books b",
        "AS avail, (SELECT MIN(due) FROM issues WHERE book_id=b.id AND returned IS NULL) AS back FROM books b")
    sql += " WHERE (b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)"
    args = [f"%{term}%"] * 3
    if cat:
        sql += " AND b.category=?"
        args.append(cat)
    cats = [r["category"] for r in q("SELECT DISTINCT category FROM books ORDER BY category")]
    return render_template("catalogue.html", books=q(sql + " ORDER BY b.title", args), cats=cats, term=term, cat=cat)


@app.route("/me/profile", methods=["GET", "POST"])
@member_required
def profile():
    m = q("SELECT * FROM members WHERE id=?", (session["mid"],), one=True)
    if request.method == "POST":
        name, phone, pw = (request.form["name"].strip(), request.form["phone"].strip(),
                           request.form.get("password", ""))
        if not name or (pw and len(pw) < 6):
            flash("Name is required and a new password needs at least 6 characters.", "error")
        else:
            run("UPDATE members SET name=?, phone=? WHERE id=?", (name, phone, m["id"]))
            if pw:
                run("UPDATE members SET password=? WHERE id=?", (generate_password_hash(pw), m["id"]))
            session["user"] = name
            flash("Profile saved.", "ok")
            return redirect(url_for("me"))
    fields = [("name", "Full name", "text"), ("phone", "Phone", "text"),
              ("password", "New password (blank keeps current)", "password")]
    return render_template("form.html", title="Your profile", fields=fields, v=m, back=url_for("me"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
