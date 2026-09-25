from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DATABASE = "smartbiz.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            receipt_number TEXT NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT NOT NULL,
            date TEXT NOT NULL,
            profit REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cheques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cheque_number TEXT NOT NULL,
            customer TEXT,
            amount REAL NOT NULL,
            bank TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            invoice_number TEXT NOT NULL,
            customer TEXT NOT NULL,
            date TEXT NOT NULL,
            due_date TEXT,
            total REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Unpaid',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            buying_price REAL NOT NULL,
            selling_price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            low_stock_level INTEGER NOT NULL DEFAULT 5,
            date_added TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Upgrade older databases that don't yet have the profit column
    columns = conn.execute("PRAGMA table_info(receipts)").fetchall()
    column_names = [column["name"] for column in columns]

    if "profit" not in column_names:
        conn.execute("""
            ALTER TABLE receipts
            ADD COLUMN profit REAL NOT NULL DEFAULT 0
        """)

    conn.commit()
    conn.close()


# ---------------- HOME ----------------

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:
            conn.execute("""
                INSERT INTO users (username, password)
                VALUES (?, ?)
            """, (username, hashed_password))

            conn.commit()
            flash("Registration successful. Please log in.")

        except sqlite3.IntegrityError:
            flash("Username already exists.")

        finally:
            conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute("""
            SELECT * FROM users
            WHERE username = ?
        """, (username,)).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")

    return render_template("login.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    sales_row = conn.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    expenses_row = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = ?
        AND type = 'expense'
    """, (user_id,)).fetchone()

    receipts_count_row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    product_profit_row = conn.execute("""
        SELECT COALESCE(SUM(profit), 0) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    recent_transactions = conn.execute("""
        SELECT *
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (user_id,)).fetchall()

    low_stock = conn.execute("""
        SELECT *
        FROM products
        WHERE user_id = ?
        AND stock <= low_stock_level
        ORDER BY stock ASC
    """, (user_id,)).fetchall()

    conn.close()

    sales = sales_row["total"]
    expenses = expenses_row["total"]
    receipts_count = receipts_count_row["total"]
    product_profit = product_profit_row["total"]

    profit = sales - expenses

    return render_template(
        "dashboard.html",
        sales=sales,
        expenses=expenses,
        profit=profit,
        receipts_count=receipts_count,
        product_profit=product_profit,
        recent_transactions=recent_transactions,
        low_stock=low_stock
    )


# ---------------- RECEIPTS ----------------

@app.route("/receipt", methods=["GET", "POST"])
def receipt():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        item = request.form.get("item", "").strip()
        quantity_text = request.form.get("quantity", "0")
        payment_method = request.form.get(
            "payment_method",
            "Cash"
        )

        try:
            quantity = int(quantity_text)
        except ValueError:
            quantity = 0

        if not item or quantity <= 0:
            conn.close()
            flash("Enter a valid product and quantity.")
            return redirect(url_for("receipt"))

        product = conn.execute("""
            SELECT *
            FROM products
            WHERE user_id = ?
            AND name = ?
        """, (user_id, item)).fetchone()

        if not product:
            conn.close()
            flash("Product not found in inventory.")
            return redirect(url_for("receipt"))

        if quantity > product["stock"]:
            conn.close()
            flash(
                f"Not enough stock. Available stock: {product['stock']}"
            )
            return redirect(url_for("receipt"))

        buying_price = product["buying_price"]
        selling_price = product["selling_price"]

        total = selling_price * quantity
        profit = (selling_price - buying_price) * quantity

        receipt_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM receipts
            WHERE user_id = ?
        """, (user_id,)).fetchone()["total"]

        receipt_number = f"REC-{receipt_count + 1:05d}"

        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
            INSERT INTO receipts
            (
                user_id,
                receipt_number,
                item,
                quantity,
                price,
                total,
                payment_method,
                date,
                profit
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            receipt_number,
            item,
            quantity,
            selling_price,
            total,
            payment_method,
            date_now,
            profit
        ))

        conn.execute("""
            INSERT INTO transactions
            (
                user_id,
                type,
                amount,
                description,
                date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            "income",
            total,
            f"Sale: {item}",
            date_now
        ))

        conn.execute("""
            UPDATE products
            SET stock = stock - ?
            WHERE id = ?
        """, (quantity, product["id"]))

        conn.commit()
        conn.close()

        return render_template(
            "receipt_result.html",
            receipt_number=receipt_number,
            item=item,
            quantity=quantity,
            price=selling_price,
            total=total,
            payment_method=payment_method,
            buying_price=buying_price,
            profit=profit,
            date=date_now
        )

    products = conn.execute("""
        SELECT *
        FROM products
        WHERE user_id = ?
        ORDER BY name ASC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "receipt.html",
        products=products
    )


# ---------------- EXPENSES ----------------

@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        description = request.form.get("description", "").strip()

        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0

        if not description or amount <= 0:
            flash("Enter a valid expense.")
            return redirect(url_for("expenses"))

        conn = get_db()

        conn.execute("""
            INSERT INTO transactions
            (
                user_id,
                type,
                amount,
                description,
                date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            "expense",
            amount,
            description,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        flash("Expense saved successfully.")
        return redirect(url_for("expenses"))

    conn = get_db()

    expenses_list = conn.execute("""
        SELECT *
        FROM transactions
        WHERE user_id = ?
        AND type = 'expense'
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expenses_list
    )


# ---------------- INVENTORY ----------------

@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        try:
            buying_price = float(
                request.form.get("buying_price", 0)
            )
            selling_price = float(
                request.form.get("selling_price", 0)
            )
            stock = int(
                request.form.get("stock", 0)
            )
            low_stock_level = int(
                request.form.get("low_stock_level", 5)
            )
        except ValueError:
            conn.close()
            flash("Enter valid numbers.")
            return redirect(url_for("inventory"))

        if (
            not name
            or buying_price < 0
            or selling_price < 0
            or stock < 0
        ):
            conn.close()
            flash("Please enter valid product information.")
            return redirect(url_for("inventory"))

        conn.execute("""
            INSERT INTO products
            (
                user_id,
                name,
                buying_price,
                selling_price,
                stock,
                low_stock_level,
                date_added
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            name,
            buying_price,
            selling_price,
            stock,
            low_stock_level,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        flash("Product added successfully.")
        return redirect(url_for("inventory"))

    products = conn.execute("""
        SELECT *
        FROM products
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "inventory.html",
        products=products
    )


# ---------------- REPORTS ----------------

@app.route("/reports")
def reports():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    sales_row = conn.execute("""
        SELECT COALESCE(SUM(total), 0) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    expenses_row = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE user_id = ?
        AND type = 'expense'
    """, (user_id,)).fetchone()

    product_profit_row = conn.execute("""
        SELECT COALESCE(SUM(profit), 0) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    receipts_count_row = conn.execute("""
        SELECT COUNT(*) AS total
        FROM receipts
        WHERE user_id = ?
    """, (user_id,)).fetchone()

    payment_methods = conn.execute("""
        SELECT
            payment_method,
            COALESCE(SUM(total), 0) AS total
        FROM receipts
        WHERE user_id = ?
        GROUP BY payment_method
        ORDER BY total DESC
    """, (user_id,)).fetchall()

    top_products = conn.execute("""
        SELECT
            item,
            SUM(quantity) AS quantity,
            SUM(total) AS sales,
            SUM(profit) AS profit
        FROM receipts
        WHERE user_id = ?
        GROUP BY item
        ORDER BY sales DESC
        LIMIT 10
    """, (user_id,)).fetchall()

    recent_transactions = conn.execute("""
        SELECT *
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
    """, (user_id,)).fetchall()

    conn.close()

    sales = sales_row["total"]
    expenses_total = expenses_row["total"]
    product_profit = product_profit_row["total"]
    receipts_count = receipts_count_row["total"]

    profit = sales - expenses_total

    return render_template(
        "reports.html",
        sales=sales,
        expenses=expenses_total,
        profit=profit,
        product_profit=product_profit,
        receipts_count=receipts_count,
        payment_methods=payment_methods,
        top_products=top_products,
        recent_transactions=recent_transactions
    )


# ---------------- CHEQUES ----------------

@app.route("/cheques", methods=["GET", "POST"])
def cheques():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        cheque_number = request.form.get(
            "cheque_number", ""
        ).strip()

        customer = request.form.get(
            "customer", ""
        ).strip()

        bank = request.form.get(
            "bank", ""
        ).strip()

        due_date = request.form.get(
            "due_date", ""
        ).strip()

        status = request.form.get(
            "status",
            "Pending"
        )

        try:
            amount = float(
                request.form.get("amount", 0)
            )
        except ValueError:
            amount = 0

        if not cheque_number or amount <= 0:
            conn.close()
            flash("Enter valid cheque information.")
            return redirect(url_for("cheques"))

        conn.execute("""
            INSERT INTO cheques
            (
                user_id,
                cheque_number,
                customer,
                amount,
                bank,
                due_date,
                status,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            cheque_number,
            customer,
            amount,
            bank,
            due_date,
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()

    cheques_list = conn.execute("""
        SELECT *
        FROM cheques
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        "cheques.html",
        cheques=cheques_list
    )


# ---------------- INVOICES ----------------

@app.route("/invoices", methods=["GET", "POST"])
def invoices():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        customer = request.form.get(
            "customer", ""
        ).strip()

        due_date = request.form.get(
            "due_date", ""
        ).strip()

        items = request.form.getlist("item")
        quantities = request.form.getlist("quantity")
        prices = request.form.getlist("price")

        if not customer:
            conn.close()
            flash("Enter customer name.")
            return redirect(url_for("invoices"))

        invoice_count = conn.execute("""
            SELECT COUNT(*) AS total
            FROM invoices
            WHERE user_id = ?
        """, (user_id,)).fetchone()["total"]

        invoice_number = f"INV-{invoice_count + 1:05d}"

        date_now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        invoice_items = []
        grand_total = 0

        for i in range(len(items)):
       
