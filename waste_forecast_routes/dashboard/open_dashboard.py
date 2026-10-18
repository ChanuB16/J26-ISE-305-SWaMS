"""
Opens the dashboard in your web browser.

The dashboard is one web page (dashboard.html) that reads Firebase directly. This script starts a
tiny web server on your laptop (needed so the map pictures load) and opens the page.

Before the first run: open config.js and set firebaseUrl (the same URL as settings.py).

Run (inside this dashboard folder):  python open_dashboard.py
Stop: press Ctrl+C in this window.
"""
import functools
import http.server
import os
import socketserver
import webbrowser

PORT = 8000
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        url = f"http://localhost:{PORT}/dashboard.html"
        print(f"Dashboard running at {url}  (Ctrl+C to stop)")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
