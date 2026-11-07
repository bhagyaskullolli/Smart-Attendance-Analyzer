# Smart Attendance Analyser

Web-based attendance system (Flask + SQLite + HTML/CSS/JavaScript).

## How to run
1. Install Python 3.10 or later.
2. Open a terminal in this folder and install Flask:
       pip install -r requirements.txt
3. (Optional) Add FICTIONAL sample data for a demonstration:
       python seed_demo_data.py
4. Start the server:
       python app.py
5. Open http://127.0.0.1:5000 in Chrome / Edge / Firefox.
6. Log in with   username: admin    password: admin123

## Run the tests
       python -m unittest -v test_app

Before using real student data, change the demo password and set a private SECRET_KEY
environment variable.
