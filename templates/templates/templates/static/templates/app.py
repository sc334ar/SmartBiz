if __name__ == "__main__":
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

        return render_template(
            "receipt_result.html",
            customer=customer,
            item=item,
            quantity=quantity,
            price=price,
            total=total,
            payment_method=payment_method
        )

    return render_template("receipt.html")
