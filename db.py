import sqlite3

DB_NAME = "users.db"


# -----------------------------
# Initialize Database
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password)
        VALUES (?, ?)
    """, ("admin", "admin123"))

    conn.commit()
    conn.close()


# -----------------------------
# Verify Login (VULNERABLE FOR DEMO)
# -----------------------------
def verify_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ⚠️ VULNERABLE QUERY (SQL Injection works here)
    query = "SELECT * FROM users WHERE username = '" + username + "' AND password = '" + password + "'"

    print("DEBUG QUERY:", query)

    cursor.execute(query)

    user = cursor.fetchone()
    conn.close()

    return user


# -----------------------------
# Add User
# -----------------------------
def add_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False

    conn.close()
    return True


# -----------------------------
# MAIN (NO AUTO TEST NOW)
# -----------------------------
if __name__ == "__main__":
    init_db()
    print("System Ready - Run Flask App")