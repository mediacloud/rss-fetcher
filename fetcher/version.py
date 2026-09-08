
try:
    # in Python 3.11
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:
    # used by pip, only need "load"
    # type: ignore[import-not-found,unused-ignore,no-redef]
    import tomli as tomllib

try:
    with open("pyproject.toml", "rb") as fp:
        VERSION = tomllib.load(fp)["project"]["version"]
except:
    VERSION = "unknown"
