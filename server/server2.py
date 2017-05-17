import threading
import webbrowser
import BaseHTTPServer
import SimpleHTTPServer

FILE = '../visualizationProject/public_html/Data/R2.2.0-R.2.7.0_comments.json'
PORT = 8080


class TestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """The test example handler."""

    def do_GET(self):
        """Handle a get request"""
        file = open(FILE)
        self.wfile.write(file.read())

def start_server():
    """Start the server."""
    server_address = ("", PORT)
    server = BaseHTTPServer.HTTPServer(server_address, TestHandler)
    server.serve_forever()

if __name__ == "__main__":
    start_server()