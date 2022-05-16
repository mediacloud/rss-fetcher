import logging
from flask import jsonify, send_from_directory
from typing import List, Dict
from itertools import chain

import fetcher
from fetcher import create_flask_app
import fetcher.database.models as models

logger = logging.getLogger(__name__)

app = create_flask_app()


def _prep_for_graph(counts: List[List], names: List[str]) -> List[Dict]:
    cleaned_data = [{r['day'].strftime("%Y-%m-%d"): r['stories'] for r in series} for series in counts]
    dates = set(chain(*[series.keys() for series in cleaned_data]))
    stories_by_day_data = []
    for d in dates:  # need to make sure there is a pair of entries for each date
        for idx, series in enumerate(cleaned_data):
            stories_by_day_data.append(dict(
                date=d,
                type=names[idx],
                count=series[d] if d in series else 0
            ))
    return stories_by_day_data


@app.route("/", methods=['GET'])
def home():
    return jsonify(dict(
        version=fetcher.VERSION,
        published_history=_prep_for_graph([models.Story.recent_published_volume()], ["stories"]),
        fetched_history=_prep_for_graph([models.Story.recent_fetched_volume()], ["stories"])
    ))


@app.route("/rss/<filename>", methods=['GET'])
def rss(filename):
    return send_from_directory(directory='static', path='rss', filename=filename)


if __name__ == "__main__":
    app.debug = True
    app.run()
