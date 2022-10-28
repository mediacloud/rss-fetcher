"""
Startup script for rss-fetcher web server

Takes common rss-fetcher logging arguments
"""
import os

import uvicorn
import uvicorn.config

# local
from fetcher.logargparse import LEVEL_DEST, LogArgumentParser
from fetcher.stats import Stats
import server

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

    # info logging before this call unlikely to be seen:
    args = p.my_parse_args()       # parse logging args, output start message

    Stats.init(SCRIPT)

    # disable uvicorn stdio logging:
    # https://github.com/tiangolo/fastapi/issues/1508#issuecomment-723457712
    log_config = None

    uvicorn.run(server.app,
                host=args.host,
                log_config=log_config,
                port=args.port,
                timeout_keep_alive=500)
