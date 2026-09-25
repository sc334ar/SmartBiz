from flask import Flask, render_template, request, redirect, url_for, session
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
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
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
            bank TEXT NOT NULL,
            payee TEXT NOT NULL,
            amount REAL NOT NULL,
            issue_date TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            invoice_number TEXT NOT NULL,
            customer TEXT NOT NULL,
            date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL
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

    conn.commit()
    conn.close()


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db()

            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed_password)
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return "Email already registered."

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        return "Invalid email or password."

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    transactions = conn.execute(
        """
        SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    sales = sum(
        t["amount"]
        for t in transactions
        if t["transaction_type"] == "income"
    )

    expenses = sum(
        t["amount"]
        for t in transactions
        if t["transaction_type"] == "expense"
    )

    profit = sales - expenses

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        transactions=transactions,
        sales=sales,
        expenses=expenses,
        profit=profit
    )


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


@app.route("/receipt", methods=["GET", "POST"])
def receipt():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        customer = request.form["customer"]
        item = request.form["item"]
        quantity = int(request.form["quantity"])
        price = float(request.form["price"])
        payment_method = request.form["payment_method"]

        total = quantity * price
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()

        last_receipt = conn.execute(
            """
            SELECT id FROM receipts
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if last_receipt:
            receipt_number = f"REC-{last_receipt['id'] + 1:05d}"
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

    return render_template("receipt.html")


@app.route("/expense", methods=["GET", "POST"])
def expense():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        description = request.form["description"]
        amount = float(request.form["amount"])
        payment_method = request.form["payment_method"]

        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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


@app.route("/cheques", methods=["GET", "POST"])
def cheques():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        cheque_number = request.form["cheque_number"]
        bank = request.form["bank"]
        payee = request.form["payee"]
        amount = float(request.form["amount"])
        issue_date = request.form["issue_date"]
        status = request.form["status"]
        notes = request.form["notes"]

        conn = get_db()

        conn.execute(
            """
            INSERT INTO cheques
            (
                user_id,
                cheque_number,
                bank,
                payee,
                amount,
                issue_date,
                status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                cheque_number,
                bank,
                payee,
                amount,
                issue_date,
                status,
                notes
            )
        )

        conn.commit()
        conn.close()

        return redirect(url_for("cheques"))

    conn = get_db()

    cheque_list = conn.execute(
        """
        SELECT * FROM cheques
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "cheques.html",
        cheques=cheque_list
    )


@app.route("/invoice", methods=["GET", "POST"])
def invoice():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        customer = request.form["customer"]
        due_date = request.form["due_date"]

        items = request.form.getlist("item[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("price[]")

        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()

        last_invoice = conn.execute(
            """
            SELECT id FROM invoices
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if last_invoice:
            invoice_number = f"INV-{last_invoice['id'] + 1:05d}"
        else:
            invoice_number = "INV-00001"

        cursor = conn.execute(
            """
            INSERT INTO invoices
            (
                user_id,
                invoice_number,
                customer,
                date,
                due_date,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                invoice_number,
                customer,
                date,
                due_date,
                "Unpaid"
            )
        )

        invoice_id = cursor.lastrowid

        invoice_items = []
        total_invoice = 0

        for item, quantity, price in zip(
            items,
            quantities,
            prices
        ):

            quantity = int(quantity)
            price = float(price)

            item_total = quantity * price
            total_invoice += item_total

            invoice_items.append({
                "item": item,
                "quantity": quantity,
                "price": price,
                "total": item_total
            })

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
                    item,
                    quantity,
                    price,
                    item_total
                )
            )

        conn.commit()
        conn.close()

        return render_template(
            "invoice_result.html",
            invoice_number=invoice_number,
            customer=customer,
            date=date,
            due_date=due_date,
            items=invoice_items,
            total=total_invoice
        )

    return render_template("invoice.html")


@app.route("/reports")
def reports():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    sales_result = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'income'
        """,
        (session["user_id"],)
    ).fetchone()

    sales = sales_result[0]

    expenses_result = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
        AND transaction_type = 'expense'
        """,
        (session["user_id"],)
    ).fetchone()

    expenses = expenses_result[0]

    profit = sales - expenses

    receipt_result = conn.execute(
        """
        SELECT COUNT(*)
        FROM receipts
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    receipt_count = receipt_result[0]

    invoice_result = conn.execute(
        """
        SELECT COUNT(*)
        FROM invoices
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    invoice_count = invoice_result[0]

    cheque_result = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM cheques
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    cheque_total = cheque_result[0]

    conn.close()

    return render_template(
        "reports.html",
        sales=sales,
        expenses=expenses,
        profit=profit,
        receipt_count=receipt_count,
        invoice_count=invoice_count,
        cheque_total=cheque_total
    )


create_database()

if __name__ == "__main__":
    app.run(debug=True)
