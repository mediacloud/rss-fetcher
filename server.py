import logging
from flask import jsonify, send_from_directory

import fetcher
from fetcher import create_flask_app

logger = logging.getLogger(__name__)

app = create_flask_app()


@app.route("/", methods=['GET'])
def home():
    return jsonify(dict(
        version=fetcher.VERSION
    ))


@app.route("/rss/<filename>", methods=['GET'])
def rss(filename):
    return send_from_directory(directory='static', path='rss', filename=filename)


if __name__ == "__main__":
    app.debug = True
    app.run()
