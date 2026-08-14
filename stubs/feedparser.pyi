from typing import TypedDict

class FeedEntry(TypedDict, total=False):
    link: str | None
    guid: str
    title: str
    published_ft: str | None

class ParsedFeed(TypedDict):
    title: str
    sy_updatefrequency: str
    sy_updateperiod: str

class FeedParserDict(TypedDict):
    version: str
    feed: ParsedFeed
    entries: list[FeedEntry]

def parse(input: bytes) -> FeedParserDict:
    ...
