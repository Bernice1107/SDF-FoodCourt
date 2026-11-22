from pathlib import Path
import os
import sqlite3
import secrets
from datetime import date

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
# A fixed key keeps the classroom demo easy to restart; set SECRET_KEY for a private deployment.
app.secret_key = os.environ.get("SECRET_KEY", "food-court-classroom-demo-only")
DATABASE = Path(__file__).parent / "food_court.db"
DELIVERY_FEE = 4000
DEPOSIT_PAISE = 10000
DINING_SLOTS = ("12:00", "13:30", "19:00", "20:30")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_orders():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, customer TEXT NOT NULL, restaurant_name TEXT NOT NULL,
            service TEXT NOT NULL, address TEXT NOT NULL, subtotal INTEGER NOT NULL,
            delivery_fee INTEGER NOT NULL, total INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
            item_name TEXT NOT NULL, unit_price INTEGER NOT NULL, quantity INTEGER NOT NULL
        );
    """)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS paid_orders (
            id INTEGER PRIMARY KEY, checkout_token TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL REFERENCES demo_users(id), restaurant_name TEXT NOT NULL,
            service TEXT NOT NULL, address TEXT NOT NULL, subtotal_paise INTEGER NOT NULL,
            delivery_fee_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS paid_order_items (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES paid_orders(id),
            item_name TEXT NOT NULL, unit_price_paise INTEGER NOT NULL, quantity INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES paid_orders(id),
            status TEXT NOT NULL CHECK (status = 'success'), amount_paise INTEGER NOT NULL,
            method TEXT NOT NULL DEFAULT 'Demo payment', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS dining_tables (
            id INTEGER PRIMARY KEY, restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            table_number INTEGER NOT NULL, capacity INTEGER NOT NULL CHECK (capacity > 0),
            UNIQUE (restaurant_id, table_number)
        );
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES demo_users(id),
            table_id INTEGER NOT NULL REFERENCES dining_tables(id),
            booking_date TEXT NOT NULL, time_slot TEXT NOT NULL, party_size INTEGER NOT NULL,
            deposit_paise INTEGER NOT NULL, booking_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (table_id, booking_date, time_slot)
        );
    """)
    db.execute("""
        INSERT OR IGNORE INTO dining_tables (restaurant_id, table_number, capacity)
        SELECT id, 1, 2 FROM restaurants
    """)
    db.execute("""
        INSERT OR IGNORE INTO dining_tables (restaurant_id, table_number, capacity)
        SELECT id, 2, 4 FROM restaurants
    """)
    db.execute("""
        INSERT OR IGNORE INTO dining_tables (restaurant_id, table_number, capacity)
        SELECT id, 3, 6 FROM restaurants
    """)
    order_columns = {row["name"] for row in db.execute("PRAGMA table_info(paid_orders)")}
    if "restaurant_id" not in order_columns:
        db.execute("ALTER TABLE paid_orders ADD COLUMN restaurant_id INTEGER REFERENCES restaurants(id)")
        db.execute("""UPDATE paid_orders SET restaurant_id =
            (SELECT id FROM restaurants WHERE restaurants.name = paid_orders.restaurant_name)""")
    if "order_status" not in order_columns:
        db.execute("ALTER TABLE paid_orders ADD COLUMN order_status TEXT NOT NULL DEFAULT 'Placed'")
    reservation_columns = {row["name"] for row in db.execute("PRAGMA table_info(reservations)")}
    if "reservation_status" not in reservation_columns:
        db.execute("ALTER TABLE reservations ADD COLUMN reservation_status TEXT NOT NULL DEFAULT 'Confirmed'")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS demo_managers (
            id INTEGER PRIMARY KEY, identifier TEXT NOT NULL UNIQUE,
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id)
        );
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY, restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            description TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            UNIQUE (restaurant_id, description)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL UNIQUE REFERENCES paid_orders(id),
            user_id INTEGER NOT NULL REFERENCES demo_users(id),
            restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            review_text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.executemany("""INSERT OR IGNORE INTO demo_managers (identifier, restaurant_id)
        SELECT ?, id FROM restaurants WHERE name = ?""", [
            ("curry.manager", "Curry Leaf Kitchen"), ("copper.manager", "Copper Spoon")])
    db.executemany("""INSERT OR IGNORE INTO offers (restaurant_id, description, start_date, end_date)
        SELECT id, ?, '2020-01-01', '2099-12-31' FROM restaurants WHERE name = ?""", [
            ("Ask about our weekday lunch special.", "Curry Leaf Kitchen"),
            ("Ask about our family dining special.", "Copper Spoon")])
    db.commit()


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def cart_details():
    cart = session.get("cart", {})
    items = []
    for item_id, quantity in cart.items():
        row = get_db().execute("""
            SELECT m.id, m.name, m.price * 100 AS price, m.available, r.id AS restaurant_id, r.name AS restaurant_name
            FROM menu_items AS m JOIN restaurants AS r ON r.id = m.restaurant_id
            WHERE m.id = ?
        """, (item_id,)).fetchone()
        if row:
            items.append({**dict(row), "quantity": quantity, "line_total": row["price"] * quantity})
    return items, sum(item["line_total"] for item in items)


@app.route("/")
def food_and_drinks():
    items, subtotal = cart_details()
    return render_template("index.html", cart_items=items, subtotal=subtotal,
                           customer=session.get("customer"))


@app.route("/api/restaurants")
def restaurants():
    locality = request.args.get("locality", "").strip()
    cuisine = request.args.get("cuisine", "").strip()
    preference = request.args.get("preference", "").strip()
    if preference not in ("", "Veg", "Non-Veg"):
        return jsonify(error="Invalid food preference."), 400
    # A restaurant appears only when it has a menu item matching the preference.
    rows = get_db().execute("""
        SELECT r.id, r.name, r.locality, r.cuisine,
               m.id AS item_id, m.name AS item_name, m.preference, m.price
        FROM restaurants AS r JOIN menu_items AS m ON m.restaurant_id = r.id
        WHERE (? = '' OR r.locality = ?) AND (? = '' OR r.cuisine = ?)
          AND (? = '' OR m.preference = ?) AND m.available = 1
        ORDER BY r.name, m.name
    """, (locality, locality, cuisine, cuisine, preference, preference)).fetchall()
    results = {}
    for row in rows:
        restaurant = results.setdefault(row["id"], {
            "id": row["id"], "name": row["name"],
            "locality": row["locality"], "cuisine": row["cuisine"], "menu": []
        })
        restaurant["menu"].append({"id": row["item_id"], "name": row["item_name"],
                                   "preference": row["preference"], "price": row["price"]})
    for restaurant in results.values():
        summary = get_db().execute("SELECT AVG(rating) AS average, COUNT(*) AS count FROM reviews WHERE restaurant_id = ?", (restaurant["id"],)).fetchone()
        restaurant["rating"] = round(summary["average"], 1) if summary["count"] else None
        restaurant["review_count"] = summary["count"]
        restaurant["offers"] = [row["description"] for row in get_db().execute("""SELECT description FROM offers
            WHERE restaurant_id = ? AND start_date <= date('now', 'localtime') AND end_date >= date('now', 'localtime') ORDER BY id""", (restaurant["id"],))]
    return jsonify(list(results.values()))


@app.post("/cart/add")
def add_to_cart():
    item = get_db().execute("SELECT id, restaurant_id FROM menu_items WHERE id = ? AND available = 1",
                            (request.form.get("item_id", ""),)).fetchone()
    if item is None:
        abort(404)
    items, _ = cart_details()
    if items and items[0]["restaurant_id"] != item["restaurant_id"]:
        flash("Your cart contains items from another restaurant. Remove them before adding this item.")
    else:
        cart = dict(session.get("cart", {}))
        key = str(item["id"])
        if cart.get(key, 0) >= 20:
            flash("You can add up to 20 of each item.")
        else:
            cart[key] = cart.get(key, 0) + 1
            session["cart"] = cart
            session["checkout_token"] = secrets.token_urlsafe(32)
            flash("Added to your cart.")
    return redirect(url_for("food_and_drinks", _anchor="cart"))


@app.post("/cart/update")
def update_cart():
    cart = dict(session.get("cart", {}))
    item_id = request.form.get("item_id", "")
    if item_id not in cart:
        abort(404)
    try:
        quantity = 0 if request.form.get("remove") else int(request.form.get("quantity", ""))
    except ValueError:
        quantity = -1
    if quantity == 0:
        cart.pop(item_id)
    elif 1 <= quantity <= 20:
        cart[item_id] = quantity
    else:
        flash("Enter a quantity from 1 to 20, or use Remove.")
    session["cart"] = cart
    session["checkout_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("food_and_drinks", _anchor="cart"))


@app.route("/sign-in", methods=["GET", "POST"])
def sign_in():
    if request.method == "POST":
        customer = request.form.get("customer", "").strip().lower()
        otp = request.form.get("otp", "").strip()
        user = get_db().execute("SELECT id, identifier FROM demo_users WHERE identifier = ?", (customer,)).fetchone()
        if not user or otp != "123456":
            flash("Use a listed demo user and demo OTP 123456.")
        else:
            session["customer"] = user["identifier"]
            session["user_id"] = user["id"]
            flash("Signed in. Your cart is still available.")
            restaurant_id = session.pop("pending_restaurant", None)
            if restaurant_id:
                return redirect(url_for("book_table", restaurant_id=restaurant_id))
            return redirect(url_for("checkout"))
    return render_template("sign_in.html")


@app.post("/sign-out")
def sign_out():
    session.pop("customer", None)
    session.pop("user_id", None)
    flash("Signed out. Your cart is still available.")
    return redirect(url_for("food_and_drinks"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    db = get_db()
    service = request.values.get("service", "Takeaway")
    if service not in ("Takeaway", "Delivery"):
        abort(400)
    address = request.values.get("address", "").strip()
    fee = DELIVERY_FEE if service == "Delivery" else 0
    if request.method == "POST":
        if not session.get("user_id"):
            flash("Sign in before confirming your order.")
            return redirect(url_for("sign_in"))
        token = request.form.get("checkout_token", "")
        existing = db.execute("SELECT id FROM paid_orders WHERE checkout_token = ? AND user_id = ?", (token, session["user_id"])).fetchone()
        if existing:
            flash("This order was already placed; no second payment was made.")
            return redirect(url_for("history"))
        if not token or token != session.get("checkout_token"):
            flash("This checkout is no longer current. Review your cart again.")
            return redirect(url_for("food_and_drinks", _anchor="cart"))
        ids = request.form.getlist("item_id")
        quantities = request.form.getlist("quantity")
        try:
            submitted = {str(int(i)): int(q) for i, q in zip(ids, quantities)}
        except ValueError:
            abort(400)
        if len(ids) != len(quantities) or len(submitted) != len(ids) or submitted != session.get("cart", {}):
            flash("Your cart changed. Review it before confirming.")
            return redirect(url_for("food_and_drinks", _anchor="cart"))
        if service == "Delivery" and not address:
            flash("Enter a delivery address before confirming your order.")
        elif request.form.get("payment") not in ("success", "failure"):
            flash("Choose a simulated payment result.")
        elif request.form["payment"] == "failure":
            flash("Payment declined (demo). Your cart has been kept; try again.")
        else:
            try:
                # Lock the database before reading current prices and availability, then save everything together.
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id FROM paid_orders WHERE checkout_token = ? AND user_id = ?", (token, session["user_id"])).fetchone()
                if existing:
                    db.rollback()
                    flash("This order was already placed; no second payment was made.")
                    return redirect(url_for("history"))
                items, subtotal = cart_details()
                if (not items or len(items) != len(submitted) or any(not i["available"] for i in items)
                        or len({i["restaurant_id"] for i in items}) != 1
                        or any(not 1 <= i["quantity"] <= 20 for i in items)):
                    db.rollback()
                    flash("An item is unavailable or the cart is invalid. Please update your cart.")
                    return redirect(url_for("food_and_drinks", _anchor="cart"))
                cursor = db.execute("""
                    INSERT INTO paid_orders (checkout_token, user_id, restaurant_name, service, address, subtotal_paise, delivery_fee_paise, total_paise, restaurant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (token, session["user_id"], items[0]["restaurant_name"], service,
                      address if service == "Delivery" else "", subtotal, fee, subtotal + fee, items[0]["restaurant_id"]))
                db.executemany("""
                    INSERT INTO paid_order_items (order_id, item_name, unit_price_paise, quantity) VALUES (?, ?, ?, ?)
                """, [(cursor.lastrowid, i["name"], i["price"], i["quantity"]) for i in items])
                db.execute("INSERT INTO payments (order_id, status, amount_paise) VALUES (?, ?, ?)",
                           (cursor.lastrowid, "success", subtotal + fee))
                db.commit()
            except Exception:
                db.rollback()
                raise
            session.pop("cart", None)
            session.pop("checkout_token", None)
            flash("Payment successful (demo). Your order was placed.")
            return redirect(url_for("history"))
    items, subtotal = cart_details()
    if not items:
        flash("Your cart is empty.")
        return redirect(url_for("food_and_drinks", _anchor="cart"))
    if not session.get("checkout_token"):
        session["checkout_token"] = secrets.token_urlsafe(32)
    return render_template("checkout.html", items=items, subtotal=subtotal, service=service,
                           address=address, fee=fee, customer=session.get("customer"),
                           checkout_token=session["checkout_token"])


@app.route("/restaurants/<int:restaurant_id>/book", methods=["GET", "POST"])
def book_table(restaurant_id):
    db = get_db()
    restaurant = db.execute("SELECT id, name FROM restaurants WHERE id = ?", (restaurant_id,)).fetchone()
    if not restaurant:
        abort(404)
    if not session.get("user_id"):
        session["pending_restaurant"] = restaurant_id
        flash("Sign in to book a table. Your cart will be kept.")
        return redirect(url_for("sign_in"))

    booking_date = request.form.get("booking_date", "")
    time_slot = request.form.get("time_slot", "")
    party_size = request.form.get("party_size", "")
    if request.method == "GET":
        session["booking_token"] = secrets.token_urlsafe(32)
    else:
        token = request.form.get("booking_token", "")
        existing = db.execute("SELECT id FROM reservations WHERE booking_token = ? AND user_id = ?",
                              (token, session["user_id"])).fetchone()
        if existing:
            flash("This reservation was already confirmed.")
            return redirect(url_for("history"))
        if not token or token != session.get("booking_token"):
            flash("This booking form has expired. Please start again.")
            return redirect(url_for("book_table", restaurant_id=restaurant_id))
        try:
            parsed_date = date.fromisoformat(booking_date)
            valid_date = parsed_date.isoformat() == booking_date and parsed_date >= date.today()
        except ValueError:
            valid_date = False
        try:
            size = int(party_size)
        except ValueError:
            size = 0
        if not valid_date:
            flash("Choose today or a future date.")
        elif time_slot not in DINING_SLOTS:
            flash("Choose one of the listed time slots.")
        elif not 1 <= size <= 6:
            flash("Choose a party size from 1 to 6.")
        elif request.form.get("payment") not in ("success", "failure"):
            flash("Choose a demo deposit result.")
        elif request.form["payment"] == "failure":
            flash("Demo deposit declined. No table was booked; your selections are kept.")
        else:
            try:
                # Serialize table selection and insertion; the UNIQUE constraint is the final safeguard.
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id FROM reservations WHERE booking_token = ? AND user_id = ?",
                                      (token, session["user_id"])).fetchone()
                if existing:
                    db.rollback()
                    flash("This reservation was already confirmed.")
                    return redirect(url_for("history"))
                table = db.execute("""
                    SELECT t.id FROM dining_tables AS t
                    WHERE t.restaurant_id = ? AND t.capacity >= ?
                      AND NOT EXISTS (
                          SELECT 1 FROM reservations AS r
                          WHERE r.table_id = t.id AND r.booking_date = ? AND r.time_slot = ?
                      )
                    ORDER BY t.capacity, t.table_number LIMIT 1
                """, (restaurant_id, size, booking_date, time_slot)).fetchone()
                if table is None:
                    db.rollback()
                    flash("No suitable table is available for this slot. Please try another slot.")
                else:
                    db.execute("""
                        INSERT INTO reservations (user_id, table_id, booking_date, time_slot, party_size, deposit_paise, booking_token)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (session["user_id"], table["id"], booking_date, time_slot, size, DEPOSIT_PAISE, token))
                    db.commit()
                    session.pop("booking_token", None)
                    flash("Demo deposit successful. Your table is confirmed.")
                    return redirect(url_for("history"))
            except sqlite3.IntegrityError:
                db.rollback()
                flash("That table is no longer available. Please try another slot.")
            except Exception:
                db.rollback()
                raise
    return render_template("reservation.html", restaurant=restaurant, slots=DINING_SLOTS,
                           today=date.today().isoformat(), booking_date=booking_date,
                           time_slot=time_slot, party_size=party_size, deposit=DEPOSIT_PAISE,
                           booking_token=session["booking_token"])


@app.get("/history")
def history():
    if not session.get("customer"):
        flash("Sign in to view your history.")
        return redirect(url_for("sign_in"))
    db = get_db()
    orders = db.execute("""
        SELECT o.*, p.status AS payment_status, p.method, p.amount_paise, p.id AS payment_id, review.id AS review_id
        FROM paid_orders AS o JOIN payments AS p ON p.order_id = o.id
        LEFT JOIN reviews AS review ON review.order_id = o.id
        WHERE o.user_id = ? ORDER BY o.id DESC
    """, (session["user_id"],)).fetchall()
    order_items = {order["id"]: db.execute(
        "SELECT * FROM paid_order_items WHERE order_id = ? ORDER BY id", (order["id"],)
    ).fetchall() for order in orders}
    legacy_orders = db.execute("SELECT * FROM orders WHERE customer = ? ORDER BY id DESC", (session["customer"],)).fetchall()
    legacy_items = {order["id"]: db.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall() for order in legacy_orders}
    reservations = db.execute("""
        SELECT r.*, t.table_number, t.capacity, restaurant.name AS restaurant_name
        FROM reservations AS r
        JOIN dining_tables AS t ON t.id = r.table_id
        JOIN restaurants AS restaurant ON restaurant.id = t.restaurant_id
        WHERE r.user_id = ? ORDER BY r.id DESC
    """, (session["user_id"],)).fetchall()
    return render_template("history.html", orders=orders, order_items=order_items,
                           legacy_orders=legacy_orders, legacy_items=legacy_items,
                           reservations=reservations)


@app.route("/manager/sign-in", methods=["GET", "POST"])
def manager_sign_in():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        manager = get_db().execute("SELECT id, identifier FROM demo_managers WHERE identifier = ?", (identifier,)).fetchone()
        if not manager or request.form.get("password") != "manager-demo":
            flash("Use a listed manager ID and the manager demo password.")
        else:
            session["manager_id"] = manager["id"]
            flash("Manager signed in.")
            return redirect(url_for("manager_page"))
    return render_template("manager_sign_in.html")


@app.post("/manager/sign-out")
def manager_sign_out():
    session.pop("manager_id", None)
    flash("Manager signed out.")
    return redirect(url_for("food_and_drinks"))


def current_manager():
    if not session.get("manager_id"):
        abort(403)
    manager = get_db().execute("""
        SELECT m.id, m.identifier, m.restaurant_id, r.name AS restaurant_name
        FROM demo_managers AS m JOIN restaurants AS r ON r.id = m.restaurant_id WHERE m.id = ?
    """, (session["manager_id"],)).fetchone()
    if not manager:
        abort(403)
    return manager


ORDER_TRANSITIONS = {
    ("Takeaway", "Placed"): "Ready for Pickup",
    ("Delivery", "Placed"): "Out for Delivery",
    ("Takeaway", "Ready for Pickup"): "Completed",
    ("Delivery", "Out for Delivery"): "Completed",
}
RESERVATION_TRANSITIONS = {"Confirmed": "Checked In", "Checked In": "Completed"}


@app.get("/manager")
def manager_page():
    manager = current_manager()
    db = get_db()
    orders = db.execute("SELECT * FROM paid_orders WHERE restaurant_id = ? ORDER BY id DESC", (manager["restaurant_id"],)).fetchall()
    reservations = db.execute("""
        SELECT r.*, t.table_number FROM reservations AS r
        JOIN dining_tables AS t ON t.id = r.table_id
        WHERE t.restaurant_id = ? ORDER BY r.id DESC
    """, (manager["restaurant_id"],)).fetchall()
    return render_template("manager.html", manager=manager, orders=orders, reservations=reservations,
                           order_transitions=ORDER_TRANSITIONS, reservation_transitions=RESERVATION_TRANSITIONS)


@app.post("/manager/orders/<int:order_id>/status")
def manager_order_status(order_id):
    manager = current_manager()
    db = get_db()
    order = db.execute("SELECT service, order_status FROM paid_orders WHERE id = ? AND restaurant_id = ?",
                       (order_id, manager["restaurant_id"])).fetchone()
    if not order:
        abort(404)
    target = request.form.get("status", "")
    if ORDER_TRANSITIONS.get((order["service"], order["order_status"])) != target:
        abort(400, "Invalid order transition.")
    updated = db.execute("UPDATE paid_orders SET order_status = ? WHERE id = ? AND restaurant_id = ? AND order_status = ?",
                         (target, order_id, manager["restaurant_id"], order["order_status"]))
    db.commit()
    if not updated.rowcount:
        abort(409, "Order status changed; reload the page.")
    flash("Order status updated.")
    return redirect(url_for("manager_page"))


@app.post("/manager/reservations/<int:reservation_id>/status")
def manager_reservation_status(reservation_id):
    manager = current_manager()
    db = get_db()
    reservation = db.execute("""SELECT r.reservation_status FROM reservations AS r
        JOIN dining_tables AS t ON t.id = r.table_id WHERE r.id = ? AND t.restaurant_id = ?""",
        (reservation_id, manager["restaurant_id"])).fetchone()
    if not reservation:
        abort(404)
    target = request.form.get("status", "")
    if RESERVATION_TRANSITIONS.get(reservation["reservation_status"]) != target:
        abort(400, "Invalid reservation transition.")
    updated = db.execute("""UPDATE reservations SET reservation_status = ? WHERE id = ? AND reservation_status = ?
        AND table_id IN (SELECT id FROM dining_tables WHERE restaurant_id = ?)""",
        (target, reservation_id, reservation["reservation_status"], manager["restaurant_id"]))
    db.commit()
    if not updated.rowcount:
        abort(409, "Reservation status changed; reload the page.")
    flash("Reservation status updated.")
    return redirect(url_for("manager_page"))


@app.get("/restaurants/<int:restaurant_id>")
def restaurant_detail(restaurant_id):
    db = get_db()
    restaurant = db.execute("SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)).fetchone()
    if not restaurant:
        abort(404)
    offers = db.execute("""SELECT * FROM offers WHERE restaurant_id = ?
        AND start_date <= date('now', 'localtime') AND end_date >= date('now', 'localtime') ORDER BY id""", (restaurant_id,)).fetchall()
    reviews = db.execute("SELECT rating, review_text, created_at FROM reviews WHERE restaurant_id = ? ORDER BY id DESC", (restaurant_id,)).fetchall()
    average = db.execute("SELECT AVG(rating) AS average, COUNT(*) AS count FROM reviews WHERE restaurant_id = ?", (restaurant_id,)).fetchone()
    return render_template("restaurant.html", restaurant=restaurant, offers=offers, reviews=reviews, average=average)


@app.post("/orders/<int:order_id>/review")
def submit_review(order_id):
    if not session.get("user_id"):
        abort(403)
    db = get_db()
    order = db.execute("SELECT restaurant_id, order_status FROM paid_orders WHERE id = ? AND user_id = ?",
                       (order_id, session["user_id"])).fetchone()
    if not order:
        abort(404)
    if order["order_status"] != "Completed" or not order["restaurant_id"]:
        abort(403, "Only completed orders can be reviewed.")
    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    review_text = request.form.get("review", "").strip()
    if not 1 <= rating <= 5 or not review_text or len(review_text) > 500:
        flash("Choose 1 to 5 stars and write a review of up to 500 characters.")
        return redirect(url_for("history"))
    try:
        db.execute("INSERT INTO reviews (order_id, user_id, restaurant_id, rating, review_text) VALUES (?, ?, ?, ?, ?)",
                   (order_id, session["user_id"], order["restaurant_id"], rating, review_text))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash("This order already has a review.")
        return redirect(url_for("history"))
    flash("Your review was saved.")
    return redirect(url_for("history"))


@app.template_filter("money")
def money(paise):
    return f"{paise // 100}.{paise % 100:02d}"


with app.app_context():
    init_orders()

if __name__ == "__main__":
    app.run(debug=True)

