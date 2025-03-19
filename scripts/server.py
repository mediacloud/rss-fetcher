"""
Startup script for rss-fetcher web server

Takes common rss-fetcher logging arguments
"""
import os

import uvicorn
import uvicorn.config

import server
# local
from fetcher.logargparse import LEVEL_DEST, LogArgumentParser

SCRIPT = 'server'

if __name__ == '__main__':
    p = LogArgumentParser(SCRIPT, 'Web API Server')

    # honor environment variable passed by Dokku:
    def_port = int(os.getenv('PORT', '8000'))
    def_host = '0.0.0.0'

    p.add_argument('--host', default=def_host, type=str,
                   help=f"addr to listen on [default: {def_host}]")

    p.add_argument('--port', default=def_port, type=int,
                   help=f"port to listen on [default: {def_port}]")

    # Tempting to add a --workers argument (like uvicorn.main has)
    # would need to pass app as a string "server.app", BUT
    # the workers die because fetcher.stats.Stats object not initialized
    # (need to do it at top level in server.__init__.py, BUT
    # cannot because Stats can only be initialized once,
    # and I (mistakenly?) pushed that down into LogArgumentParser
    # (seemed to make sense, as I was trying to make all scripts
    # send stats). -PLB (see also comment in fetcher/logargparse.py)

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    # disable uvicorn stdio logging:
    # https://github.com/tiangolo/fastapi/issues/1508#issuecomment-723457712
    log_config = None

    uvicorn.run(server.app,
                host=args.host,
                log_config=log_config,
                port=args.port,
                timeout_keep_alive=500)
