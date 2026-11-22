from pathlib import Path
import sqlite3

DATABASE = Path(__file__).parent / "food_court.db"

with sqlite3.connect(DATABASE) as db:
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            locality TEXT NOT NULL, cuisine TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY, restaurant_id INTEGER NOT NULL,
            name TEXT NOT NULL, preference TEXT NOT NULL CHECK (preference IN ('Veg', 'Non-Veg')),
            price INTEGER NOT NULL CHECK (price >= 0),
            FOREIGN KEY (restaurant_id) REFERENCES restaurants(id),
            UNIQUE (restaurant_id, name)
        );
    """)
    columns = {row[1] for row in db.execute("PRAGMA table_info(menu_items)")}
    if "available" not in columns:
        db.execute("ALTER TABLE menu_items ADD COLUMN available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1))")
    db.execute("CREATE TABLE IF NOT EXISTS demo_users (id INTEGER PRIMARY KEY, identifier TEXT NOT NULL UNIQUE)")
    db.executemany("INSERT OR IGNORE INTO demo_users (identifier) VALUES (?)", [("student@example.com",), ("demo@example.com",)])
    restaurants = [
        ("Curry Leaf Kitchen", "Malleswaram", "South Indian"),
        ("Copper Spoon", "Malleswaram", "North Indian"),
        ("Noodle Corner", "Indiranagar", "Chinese"),
        ("Garden Tiffin", "Indiranagar", "South Indian"),
    ]
    db.executemany("INSERT OR IGNORE INTO restaurants (name, locality, cuisine) VALUES (?, ?, ?)", restaurants)
    items = [
        ("Curry Leaf Kitchen", "Masala Dosa", "Veg", 120),
        ("Curry Leaf Kitchen", "Chicken Pepper Fry", "Non-Veg", 240),
        ("Copper Spoon", "Paneer Tikka", "Veg", 220),
        ("Copper Spoon", "Butter Chicken", "Non-Veg", 280),
        ("Noodle Corner", "Vegetable Noodles", "Veg", 170),
        ("Noodle Corner", "Chicken Fried Rice", "Non-Veg", 210),
        ("Garden Tiffin", "Idli and Sambar", "Veg", 90),
        ("Garden Tiffin", "Filter Coffee", "Veg", 60),
    ]
    db.executemany("""
        INSERT OR IGNORE INTO menu_items (restaurant_id, name, preference, price)
        SELECT id, ?, ?, ? FROM restaurants WHERE name = ?
    """, [(name, preference, price, restaurant) for restaurant, name, preference, price in items])
print("Database ready:", DATABASE)
