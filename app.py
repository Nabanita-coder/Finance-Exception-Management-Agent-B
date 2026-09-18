"""
app.py
------
This is the MAIN file you run to start FEMA.

What it does, in order:
1. Loads settings from .env (database password, LLM key, etc.)
2. Connects to MySQL and creates the tables if they don't exist yet
   (see dbConnection/db.py)
3. Registers all the API routes (see controllers/finance_controller.py)
4. Serves the simple browser UI (templates/index.html)
5. Starts the Flask web server

To run this file:
    python app.py

Then open your browser at:
    http://localhost:5000
"""

import os

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_cors import CORS

from dbConnection.db import init_db
from controllers.finance_controller import finance_bp

# Load .env variables (DB_HOST, DB_PASSWORD, ANTHROPIC_API_KEY, etc.)
load_dotenv()

app = Flask(__name__)

# Allow the browser UI to call our API without being blocked
# (useful if you ever host the UI separately from the API).
CORS(app)

# All routes from finance_controller.py will now live under /api/...
# e.g. /health becomes /api/health
app.register_blueprint(finance_bp, url_prefix="/api")


@app.route("/")
def home():
    """Serves the FEMA dashboard/UI page."""
    return render_template("index.html")


if __name__ == "__main__":
    # Step 1: make sure MySQL tables exist and starter owners are seeded.
    print("Connecting to MySQL and preparing tables...")
    init_db()
    print("Database ready.")

    # Step 2: start the Flask development server.
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    print(f"Starting FEMA on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
