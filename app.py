from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import requests
import json
import os
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_me")

# ── API KEYS (loaded from .env) ──────────────────────────────────────────────
AVIATIONSTACK_KEY  = os.getenv("AVIATIONSTACK_KEY", "")
OPENWEATHER_KEY    = os.getenv("OPENWEATHER_KEY", "")
AMADEUS_API_KEY    = os.getenv("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET", "")

AMADEUS_AUTH_URL   = "https://test.api.amadeus.com/v1/security/oauth2/token"
AMADEUS_FLIGHT_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"

# ── FILES ────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
FAVORITES_FILE = os.path.join(BASE_DIR, "favorites.json")
HISTORY_FILE   = os.path.join(BASE_DIR, "search_history.json")
DB_NAME        = os.path.join(BASE_DIR, "users.db")


# ── DATABASE ──────────────────────────────────────────────────────────────────
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


# ── AUTH ─────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = verify_user(username, password)
        if user:
            session["logged_in"] = True
            return redirect(url_for("home"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── JSON HELPERS ──────────────────────────────────────────────────────────────
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s", path, e)
            return []
    return []


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_route(source, destination):
    return (source or "").strip().upper(), (destination or "").strip().upper()


def dedupe_routes(routes):
    seen = set()
    unique = []
    for route in routes:
        source, destination = normalize_route(route.get("source"), route.get("destination"))
        if not source or not destination:
            continue
        flight_no = (route.get("flight_no") or "").strip().upper()
        key = (source, destination, flight_no)
        if key in seen:
            continue
        seen.add(key)
        entry = {"source": source, "destination": destination}
        if flight_no:
            entry["flight_no"] = flight_no
        if route.get("airline"):
            entry["airline"] = (route.get("airline") or "").strip()
        unique.append(entry)
    return unique


def load_favorites():
    favorites = dedupe_routes(load_json(FAVORITES_FILE))
    save_json(FAVORITES_FILE, favorites)
    return favorites


# ── AMADEUS TOKEN ─────────────────────────────────────────────────────────────
def get_amadeus_token():
    if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
        return None
    try:
        r = requests.post(
            AMADEUS_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": AMADEUS_API_KEY,
                "client_secret": AMADEUS_API_SECRET,
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("access_token")
    except requests.RequestException as e:
        logger.warning("Amadeus auth error: %s", e)
        return None


# ── FLIGHT PRICES (AMADEUS) ───────────────────────────────────────────────────
def get_amadeus_prices(source, destination):
    if not source or not destination:
        return []

    token = get_amadeus_token()
    if not token:
        return []

    try:
        r = requests.get(
            AMADEUS_FLIGHT_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "originLocationCode": source,
                "destinationLocationCode": destination,
                "departureDate": datetime.now().strftime("%Y-%m-%d"),
                "adults": 1,
                "currencyCode": "USD",
                "max": 5,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        results = []

        for item in data:
            try:
                seg = item["itineraries"][0]["segments"][0]
                results.append(
                    {
                        "airline": seg.get("carrierCode"),
                        "flight_no": seg.get("number"),
                        "dep_time": seg["departure"]["at"].replace("T", " "),
                        "arr_time": seg["arrival"]["at"].replace("T", " "),
                        "duration": item["itineraries"][0].get("duration"),
                        "stops": len(item["itineraries"][0]["segments"]) - 1,
                        "price_usd": float(item["price"]["total"]),
                        "price_pkr": round(float(item["price"]["total"]) * 280),
                    }
                )
            except (KeyError, IndexError, ValueError, TypeError) as e:
                logger.debug("Skipping malformed flight offer: %s", e)
                continue

        if results:
            results.sort(key=lambda x: x["price_usd"])
            results[0]["badge"] = "Cheapest"

        return results

    except requests.RequestException as e:
        logger.warning("Amadeus price lookup error: %s", e)
        return []


# ── LIVE FLIGHTS (AVIATIONSTACK) ──────────────────────────────────────────────
def get_flights(source, destination):
    if not AVIATIONSTACK_KEY or not source or not destination:
        return []

    try:
        r = requests.get(
            "http://api.aviationstack.com/v1/flights",
            params={
                "access_key": AVIATIONSTACK_KEY,
                "dep_iata": source,
                "arr_iata": destination,
                "limit": 10,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        flights = []

        for f in data:
            flights.append(
                {
                    "departure": f.get("departure", {}),
                    "arrival": f.get("arrival", {}),
                    "airline": f.get("airline", {}),
                    "flight": f.get("flight", {}),
                    "flight_status": f.get("flight_status", "unknown"),
                }
            )

        return flights

    except requests.RequestException as e:
        logger.warning("Aviationstack lookup error: %s", e)
        return []


# ── WEATHER ───────────────────────────────────────────────────────────────────
def get_weather(city):
    if not OPENWEATHER_KEY or not city:
        return None

    try:
        geo_resp = requests.get(
            "http://api.openweathermap.org/geo/1.0/direct",
            params={"q": city, "limit": 1, "appid": OPENWEATHER_KEY},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo = geo_resp.json()

        if not geo:
            return None

        lat, lon = geo[0]["lat"], geo[0]["lon"]

        w_resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_KEY},
            timeout=10,
        )
        w_resp.raise_for_status()
        w = w_resp.json()

        return {
            "city": geo[0].get("name"),
            "temp": round(w.get("main", {}).get("temp", 0)),
            "feels_like": round(w.get("main", {}).get("feels_like", 0)),
            "temp_min": round(w.get("main", {}).get("temp_min", 0)),
            "temp_max": round(w.get("main", {}).get("temp_max", 0)),
            "desc": w.get("weather", [{}])[0].get("description", "").title(),
            "icon": w.get("weather", [{}])[0].get("icon"),
            "humidity": w.get("main", {}).get("humidity"),
            "wind_kph": round(w.get("wind", {}).get("speed", 0) * 3.6),
            "visibility_km": round(w.get("visibility", 0) / 1000, 1),
            "cloudiness": w.get("clouds", {}).get("all"),
            "pressure_hpa": w.get("main", {}).get("pressure"),
            "sunrise": datetime.fromtimestamp(w.get("sys", {}).get("sunrise", 0)).strftime("%H:%M"),
            "sunset": datetime.fromtimestamp(w.get("sys", {}).get("sunset", 0)).strftime("%H:%M"),
        }

    except requests.RequestException as e:
        logger.warning("Weather lookup error: %s", e)
        return None


# ── HOME ROUTE ────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def home():
    source      = request.args.get("source", "").strip().upper()
    destination = request.args.get("destination", "").strip().upper()

    flights = []
    weather = None
    prices  = []
    error   = None

    if source and destination:
        try:
            flights = get_flights(source, destination)
            weather = get_weather(destination)
            prices  = get_amadeus_prices(source, destination)

            history = load_json(HISTORY_FILE)
            history.append(
                {
                    "source": source,
                    "destination": destination,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "count": len(flights),
                }
            )
            save_json(HISTORY_FILE, history[-20:])

        except Exception:
            logger.exception("Unexpected error handling search")
            error = "Something went wrong while fetching flight data. Please try again."

    return render_template(
        "index.html",
        flights=flights,
        weather=weather,
        error=error,
        source=source,
        destination=destination,
        favorites=load_favorites(),
        history=list(reversed(load_json(HISTORY_FILE))),
        price_comparison=prices,
    )


# ── PRICES API ────────────────────────────────────────────────────────────────
@app.route("/prices")
@login_required
def prices_api():
    source      = request.args.get("source", "").strip().upper()
    destination = request.args.get("destination", "").strip().upper()
    return jsonify(get_amadeus_prices(source, destination))


# ── FAVORITES ─────────────────────────────────────────────────────────────────
@app.route("/favorite/add", methods=["POST"])
@login_required
def add_fav():
    data = request.get_json(silent=True) or {}
    source, destination = normalize_route(data.get("source"), data.get("destination"))

    if not source or not destination:
        return jsonify({"status": "error", "message": "source and destination are required"}), 400

    flight_no = (data.get("flight_no") or "").strip().upper()
    airline   = (data.get("airline") or "").strip()

    favs = load_favorites()
    already = any(
        f["source"] == source and f["destination"] == destination
        and (f.get("flight_no") or "") == flight_no
        for f in favs
    )
    if not already:
        entry = {"source": source, "destination": destination}
        if flight_no:
            entry["flight_no"] = flight_no
        if airline:
            entry["airline"] = airline
        favs.append(entry)
    save_json(FAVORITES_FILE, favs)
    return jsonify({"status": "ok", "favorites": favs})


@app.route("/favorite/remove", methods=["POST"])
@login_required
def remove_fav():
    data = request.get_json(silent=True) or {}
    source, destination = normalize_route(data.get("source"), data.get("destination"))
    flight_no = (data.get("flight_no") or "").strip().upper()

    favs = load_favorites()
    if flight_no:
        favs = [f for f in favs if (f.get("flight_no") or "").strip().upper() != flight_no]
    else:
        favs = [
            f for f in favs
            if not (f.get("source") == source and f.get("destination") == destination)
        ]

    save_json(FAVORITES_FILE, favs)
    return jsonify({"status": "ok", "favorites": favs})


# ── CLEAR HISTORY ─────────────────────────────────────────────────────────────
@app.route("/history/clear", methods=["POST"])
@login_required
def clear_history():
    save_json(HISTORY_FILE, [])
    return jsonify({"status": "ok"})


# ── STARTUP ───────────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    app.run(debug=True)