__author__ = 'caipeichao'

import SimpleHTTPServer
import SocketServer
import json


class JsonServer(SimpleHTTPServer.SimpleHTTPRequestHandler):
    jsonmap = {
        "/login_success": {
            "success": True,
            "message": "login success"
        },
        "/login_fail": {
            "success": False,
            "message": "internal error"
        }
    }

    def do_GET(self):
        j = self.jsonmap.get(self.path)
        if not j:
            self.send_404()
            return
        self.send_json(j)

    def send_404(self):
        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "message": "request path not found"}))
        self.wfile.close()

    def send_json(self, j):
        self.send_response(200)

        # send header first
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        # send file content to client
        self.wfile.write(json.dumps(j))
        self.wfile.close()
        return


port = 8000
httpd = SocketServer.TCPServer(("", port), JsonServer)
print("serving at port: %s" % port)
httpd.serve_forever()
