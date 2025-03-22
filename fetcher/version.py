
import tomli  # brought in by pip

try:
    with open("pyproject.toml", "rb") as fp:
        VERSION = tomli.load(fp)["project"]["version"]
except:
    VERSION = "unknown"
