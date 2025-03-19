import datetime as dt
import html
import logging
import os
from email.utils import formatdate  # RFC 822 date format
from typing import Optional, TextIO

from jinja2 import Template

from fetcher import VERSION
from fetcher.path import BASE_DIR

logger = logging.getLogger(__file__)

template_path = os.path.join(BASE_DIR, 'fetcher', 'rss')


def _escape(text: Optional[str]) -> str:
    # return a safe text string for XML output
    if text is None:
        return ''
    output = html.unescape(text)  # cleanup while we are in here
    output = output.replace("&", "&amp;")
    output = output.replace("<", "&lt;")
    output = output.replace(">", "&gt;")
    return output


def _int(val: Optional[int]) -> str:
    if val is None:
        return ''
    return str(val)


class RssWriter:
    def __init__(self, file: Optional[TextIO]):
        self.file = file
        with open(os.path.join(template_path, "item.template")) as f:
            template_str = f.read()
        self.item_template = Template(template_str)

    def add_header(self, today: dt.date) -> str:
        with open(os.path.join(template_path, "header.template")) as f:
            template_str = f.read()
            tm = Template(template_str)
        content = tm.render(
            day=today.strftime("%Y-%m-%d"),
            now=formatdate(),
            version=VERSION)
        if self.file:
            self.file.write(content)
        return content

    def add_item(self,
                 link: str, pub_date: dt.datetime,
                 domain: str, title: Optional[str],
                 feed_url: Optional[str] = None,
                 feed_id: Optional[int] = None,
                 source_id: Optional[int] = None) -> str:
        date_for_output = ""
        if pub_date is not None:
            date_for_output = formatdate(pub_date.timestamp())
        content = self.item_template.render(
            link=_escape(link), pub_date=date_for_output, domain=_escape(domain),
            title=_escape(title), feed_url=_escape(feed_url),
            sources_id=_int(source_id), feed_id=_int(feed_id))
        if self.file:
            self.file.write(content)
        return content

    def add_footer(self) -> str:
        with open(os.path.join(template_path, "footer.template")) as f:
            template_str = f.read()
        tm = Template(template_str)
        content = tm.render()
        if self.file:
            self.file.write(content)
        return content
