from astro_api import create_app

# This is the application object that WSGI servers (like Gunicorn) use
app = create_app()

if __name__ == "__main__":
    app.run()
