import os

from app.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("APP_HOST", "127.0.0.1"), port=5000, debug=app.config["DEBUG_MODE"])
