# ✈️ Flight Tracker

A Flask-based live flight tracker that brings together real-time flight data, airport/airline lookups, and weather conditions in one place — powered by the **AviationStack**, **Amadeus**, and **OpenWeather** APIs.

## Features

- 🔎 Look up live flight status and details
- 🌦️ See current weather conditions at departure/arrival airports
- 🛫 Pulls airline and flight data via the Amadeus API
- 🗄️ Persists data using a lightweight database layer (`db.py`)
- ⚡ Simple Flask web interface via server-rendered templates

## Tech Stack

- **Backend:** Python, Flask
- **Data sources:** AviationStack API, Amadeus API, OpenWeather API
- **Frontend:** Flask templates (Jinja2)

## Getting Started

### Prerequisites

- Python 3.9+
- API keys for:
  - [AviationStack](https://aviationstack.com/)
  - [Amadeus for Developers](https://developers.amadeus.com/)
  - [OpenWeather](https://openweathermap.org/api)

### Installation

```bash
# Clone the repo
git clone https://github.com/hellop11/Flight-tracker-.git
cd Flight-tracker-

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# then edit .env and add your API keys
```

### Running the app

```bash
python app.py
```

The app will be available at `http://localhost:5000` (or whichever port Flask reports).

## Environment Variables

See `.env.example` for the full list of required keys, which typically include your AviationStack, Amadeus, and OpenWeather API credentials.

## Project Structure

```
Flight-tracker-/
├── app.py              # Main Flask application
├── db.py                # Database logic
├── requirements.txt     # Python dependencies
├── .env.example          # Example environment configuration
└── templates/            # HTML templates
```

## Roadmap

- [ ] Add flight search history
- [ ] Add map visualization of flight routes
- [ ] Add user accounts / saved flights

## License

This project currently has no license specified. Consider adding one (e.g. MIT) if you plan to accept contributions.

## Acknowledgements

- [AviationStack](https://aviationstack.com/)
- [Amadeus for Developers](https://developers.amadeus.com/)
- [OpenWeather](https://openweathermap.org/)
