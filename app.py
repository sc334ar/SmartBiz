from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)

app.secret_key = "change-this-secret-key"

DATABASE = "smartbiz.db"


# =========================
# DATABASE
# =========================

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
            transaction_type TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT,
            date TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            receipt_number TEXT NOT NULL,
            customer TEXT NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cheques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cheque_number TEXT NOT NULL,
            customer TEXT NOT NULL,
            amount REAL NOT NULL,
            bank TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Pending',
            date TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            invoice_number TEXT NOT NULL,
            customer TEXT NOT NULL,
            total REAL NOT NULL,
            date TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            sku TEXT,
            buying_price REAL NOT NULL DEFAULT 0,
            selling_price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            low_stock_level INTEGER NOT NULL DEFAULT 5,
            date_added TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================
# HOME
# =========================

@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.execute(
                """
                INSERT INTO users (username, password)
                VALUES (?, ?)
                """,
                (username, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:

            conn.close()

            return "Username already exists."

    return render_template("register.html")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("dashboard"))

        return "Invalid username or password."

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    user_id = session["user_id"]

    sales = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'income'
        """,
        (user_id,)
    ).fetchone()[0]

    expenses = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'expense'
        """,
        (user_id,)
    ).fetchone()[0]

    receipts_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM receipts
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    transactions = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user_id,)
    ).fetchall()

    low_stock = conn.execute(
        """
        SELECT *
        FROM products
        WHERE user_id = ?
        AND stock <= low_stock_level
        ORDER BY stock ASC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    profit = sales - expenses

    return render_template(
        "dashboard.html",
        sales=sales,
        expenses=expenses,
        profit=profit,
        receipts_count=receipts_count,
        transactions=transactions,
        low_stock=low_stock
    )


# =========================
# RECEIPTS
# =========================

@app.route("/receipt", methods=["GET", "POST"])
def receipt():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        customer = request.form["customer"]
        item = request.form["item"]
        quantity = int(request.form["quantity"])
        payment_method = request.form["payment_method"]

        product = conn.execute(
            """
            SELECT *
            FROM products
            WHERE user_id = ?
            AND name = ?
            """,
            (session["user_id"], item)
        ).fetchone()

        if not product:

            conn.close()

            return """
            <h2>Product not found</h2>
            <p>Please add the product to inventory first.</p>
            <a href="/receipt">Back</a>
            """

        if quantity <= 0:

            conn.close()

            return """
            <h2>Invalid quantity</h2>
            <a href="/receipt">Back</a>
            """

        if quantity > product["stock"]:

            available = product["stock"]

            conn.close()

            return f"""
            <h2>⚠️ Not enough stock</h2>

            <p>Product: <strong>{item}</strong></p>

            <p>Available stock:
            <strong>{available}</strong></p>

            <p>Requested quantity:
            <strong>{quantity}</strong></p>

            <p>
                <a href="/receipt">← Back to Receipt</a>
            </p>
            """

        price = product["selling_price"]

        total = quantity * price

        date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        last_receipt = conn.execute(
            """
            SELECT id
            FROM receipts
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if last_receipt:

            receipt_number = (
                f"REC-{last_receipt['id'] + 1:05d}"
            )

        else:

            receipt_number = "REC-00001"

        conn.execute(
            """
            INSERT INTO receipts
            (
                user_id,
                receipt_number,
                customer,
                item,
                quantity,
                price,
                total,
                payment_method,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                receipt_number,
                customer,
                item,
                quantity,
                price,
                total,
                payment_method,
                date
            )
        )

        conn.execute(
            """
            INSERT INTO transactions
            (
                user_id,
                transaction_type,
                description,
                amount,
                payment_method,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                "income",
                f"Sale - {item} ({receipt_number})",
                total,
                payment_method,
                date
            )
        )

        conn.execute(
            """
            UPDATE products
            SET stock = stock - ?
            WHERE id = ?
            AND user_id = ?
            """,
            (
                quantity,
                product["id"],
                session["user_id"]
            )
        )

        conn.commit()
        conn.close()

        return render_template(
            "receipt_result.html",
            receipt_number=receipt_number,
            customer=customer,
            item=item,
            quantity=quantity,
            price=price,
            total=total,
            payment_method=payment_method,
            date=date
        )

    products = conn.execute(
        """
        SELECT *
        FROM products
        WHERE user_id = ?
        ORDER BY name ASC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "receipt.html",
        products=products
    )


# =========================
# EXPENSE
# =========================

@app.route("/expense", methods=["GET", "POST"])
def expense():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        description = request.form["description"]
        amount = float(request.form["amount"])
        payment_method = request.form["payment_method"]

        date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = get_db()

        conn.execute(
            """
            INSERT INTO transactions
            (
                user_id,
                transaction_type,
                description,
                amount,
                payment_method,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                "expense",
                description,
                amount,
                payment_method,
                date
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("expense.html")


# =========================
# CHEQUES
# =========================

@app.route("/cheques", methods=["GET", "POST"])
def cheques():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        cheque_number = request.form["cheque_number"]
        customer = request.form["customer"]
        amount = float(request.form["amount"])
        bank = request.form["bank"]
        due_date = request.form["due_date"]

        date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn.execute(
            """
            INSERT INTO cheques
            (
                user_id,
                cheque_number,
                customer,
                amount,
                bank,
                due_date,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                cheque_number,
                customer,
                amount,
                bank,
                due_date,
                date
            )
        )

        conn.commit()

    cheques_list = conn.execute(
        """
        SELECT *
        FROM cheques
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "cheques.html",
        cheques=cheques_list
    )


# =========================
# INVOICE
# =========================

@app.route("/invoice", methods=["GET", "POST"])
def invoice():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        customer = request.form["customer"]

        items = request.form.getlist("item[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")

        total = 0

        for i in range(len(items)):

            quantity = int(quantities[i])
            price = float(prices[i])

            total += quantity * price

        date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = get_db()

        last_invoice = conn.execute(
            """
            SELECT id
            FROM invoices
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if last_invoice:

            invoice_number = (
                f"INV-{last_invoice['id'] + 1:05d}"
            )

        else:

            invoice_number = "INV-00001"

        cursor = conn.execute(
            """
            INSERT INTO invoices
            (
                user_id,
                invoice_number,
                customer,
                total,
                date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                invoice_number,
                customer,
                total,
                date
            )
        )

        invoice_id = cursor.lastrowid

        for i in range(len(items)):

            quantity = int(quantities[i])
            price = float(prices[i])
            item_total = quantity * price

            conn.execute(
                """
                INSERT INTO invoice_items
                (
                    invoice_id,
                    item,
                    quantity,
                    price,
                    total
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    items[i],
                    quantity,
                    price,
                    item_total
                )
            )

        conn.commit()
        conn.close()

        return redirect(url_for("invoice"))

    return render_template("invoice.html")


# =========================
# INVENTORY
# =========================

@app.route("/inventory", methods=["GET", "POST"])
def inventory():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    if request.method == "POST":

        name = request.form["name"]
        sku = request.form["sku"]
        buying_price = float(
            request.form["buying_price"]
        )
        selling_price = float(
            request.form["selling_price"]
        )
        stock = int(request.form["stock"])
        low_stock_level = int(
            request.form["low_stock_level"]
        )

        date_added = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn.execute(
            """
            INSERT INTO products
            (
                user_id,
                name,
                sku,
                buying_price,
                selling_price,
                stock,
                low_stock_level,
                date_added
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                name,
                sku,
                buying_price,
                selling_price,
                stock,
                low_stock_level,
                date_added
            )
        )

        conn.commit()

    products = conn.execute(
        """
        SELECT *
        FROM products
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "inventory.html",
        products=products
    )


# =========================
# REPORTS
# =========================

@app.route("/reports")
def reports():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    user_id = session["user_id"]

    # -------------------------
    # SALES
    # -------------------------

    sales = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'income'
        """,
        (user_id,)
    ).fetchone()[0]

    # -------------------------
    # EXPENSES
    # -------------------------

    expenses = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'expense'
        """,
        (user_id,)
    ).fetchone()[0]

    # -------------------------
    # RECEIPTS
    # -------------------------

    receipts_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM receipts
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    # -------------------------
    # PAYMENT METHODS
    # -------------------------

    payment_methods = conn.execute(
        """
        SELECT
            payment_method,
            COALESCE(SUM(total), 0) AS total
        FROM receipts
        WHERE user_id = ?
        GROUP BY payment_method
        ORDER BY total DESC
        """,
        (user_id,)
    ).fetchall()

    # -------------------------
    # TOP PRODUCTS
    # -------------------------

    top_products = conn.execute(
        """
        SELECT
            item,
            SUM(quantity) AS quantity,
            SUM(total) AS sales
        FROM receipts
        WHERE user_id = ?
        GROUP BY item
        ORDER BY sales DESC
        LIMIT 10
        """,
        (user_id,)
    ).fetchall()

    # -------------------------
    # RECENT TRANSACTIONS
    # -------------------------

    transactions = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    # -------------------------
    # PROFIT
    # -------------------------

    profit = sales - expenses

    return render_template(
        "reports.html",
        sales=sales,
        expenses=expenses,
        profit=profit,
        receipts_count=receipts_count,
        payment_methods=payment_methods,
        top_products=top_products,
        transactions=transactions
    )

# =========================
# START DATABASE
# =========================

create_database()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
        )
