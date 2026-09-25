"""Run the local companion; deploy behind authenticated TLS for remote access."""
import argparse
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from .config import Config, load_env
from .server import create_app


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads=True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass  # API request data and credentials never belong in access logs.


def main():
    parser=argparse.ArgumentParser(description='MiroShark Strategy advisory workspace')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=5100)
    parser.add_argument('--env-file',action='append',default=[])
    args=parser.parse_args()
    for path in args.env_file: load_env(path)
    config=Config.environment()
    if len(config.token)<24: parser.error('Set STRATEGY_ACCESS_TOKEN to a secret of at least 24 characters')
    app=create_app(config)
    with make_server(args.host,args.port,app,server_class=ThreadedServer,handler_class=QuietHandler) as server:
        print(f'MiroShark Strategy listening on http://{args.host}:{args.port}. Live calls enabled: {config.live_enabled}.',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: app.close()


if __name__=='__main__': main()
