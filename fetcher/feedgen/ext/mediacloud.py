from feedgen.ext.base import BaseExtension, BaseEntryExtension
from feedgen.util import xml_elem

MEDIACLOUD_NS = 'https://mediacloud.org/dtds/mediacloud-1.0.dtd'


class MediacloudExtension(BaseExtension):

    def extend_ns(self):
        return {'mediacloud': MEDIACLOUD_NS}


class MediacloudEntryExtension(BaseEntryExtension):

    def __init__(self):
        self.__canonical_domain = None

    def extend_rss(self, entry):
        if self.canonical_domain:
            domain_node = xml_elem('{%s}canonical_domain' % MEDIACLOUD_NS, entry)
            domain_node.text = self.canonical_domain
        return entry

    def extend_atom(self, entry):
        return self.extend_rss(entry)
