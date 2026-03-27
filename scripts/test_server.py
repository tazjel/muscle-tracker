import http.server
import socketserver
import os

PORT = 8001
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

Handler = http.server.SimpleHTTPRequestHandler
Handler.extensions_map.update({
    '.glb': 'model/gltf-binary',
    '.hdr': 'application/octet-stream',
})

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
