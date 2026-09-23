from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

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


route@app.route("/receipt", methods=["GET", "POST"])
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

        # Generate receipt number
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
        t["amount"] for t in transactions
        if t["transaction_type"] == "income"
    )

    expenses = sum(
        t["amount"] for t in transactions
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


if __name__ == "__main__":
    create_database()
    app.run(debug=True)
