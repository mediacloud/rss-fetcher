# from mc-providers, from api-client/.../api.py

import importlib.metadata       # to get version for SOFTWARE_ID

try:
    VERSION = "v" + importlib.metadata.version("rss-fetcher")
except importlib.metadata.PackageNotFoundError:
    VERSION = "dev"
