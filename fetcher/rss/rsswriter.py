import datetime as dt
from email.utils import formatdate  # RFC 822 date format
import html
import logging
import os
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


def add_header(file: Optional[TextIO], today: dt.date) -> str:
    with open(os.path.join(template_path, "header.template")) as f:
        template_str = f.read()
    tm = Template(template_str)
    content = tm.render(
        day=today.strftime("%Y-%m-%d"),
        now=formatdate(),
        version=VERSION)
    if file:
        file.write(content)
    return content


def add_item(file: Optional[TextIO], link: str,
             pub_date: dt.datetime, domain: str, title: Optional[str],
             feed_url: Optional[str] = None,
             feed_id: Optional[int] = None,
             source_id: Optional[int] = None) -> str:
    with open(os.path.join(template_path, "item.template")) as f:
        template_str = f.read()
    tm = Template(template_str)
    date_for_output = ""
    if pub_date is not None:
        date_for_output = formatdate(pub_date.timestamp())
    content = tm.render(link=_escape(link), pub_date=date_for_output, domain=_escape(domain),
                        title=_escape(title), feed_url=_escape(feed_url),
                        sources_id=_int(source_id), feed_id=_int(feed_id))
    if file:
        file.write(content)
    return content


def add_footer(file: Optional[TextIO]) -> str:
    with open(os.path.join(template_path, "footer.template")) as f:
        template_str = f.read()
    tm = Template(template_str)
    content = tm.render()
    if file:
        file.write(content)
    return content
