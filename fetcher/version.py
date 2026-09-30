
import tomllib

try:
    with open("pyproject.toml", "rb") as fp:
        VERSION = tomllib.load(fp)["project"]["version"]
except:
    VERSION = "unknown"
