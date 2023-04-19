"""
This implements "config.ini" style storage made up of "sections",
each with string key and associated (string) values, stored
in a database table.

This is the THIRD attempt at an interface, and I can imagine FOURTH:
        (using Python properties (requires a singleton instance of a subclass,
        using get/set and unset by setting to None)
FIFTH, (using descriptors, which, I think wouldn't require an
        instance of the subclass, and could implement "unset" via the
        Python __delete__ method),
and a SIXTH, which presents the entire table as a dict-like object
        indexed by section, containing dict-like objects indexed by key.

I've already spent MORE than enough time on a trivial and
not (yet) much used facility!

Phil Budne
2022-12-13
"""

import logging
from typing import Dict, List, NoReturn, Optional, Type

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from fetcher.database import Session
from fetcher.database.models import Property

logger = logging.getLogger(__name__)


class Section:
    """Base class for a 'section' of properties"""
    SECTION_NAME: str = 'OVERRIDE THIS!!!'

    @classmethod
    def get_all(cls) -> Dict[str, str]:
        """
        return a dict with all key/values in a section
        """
        logger.debug(f"get_all section {cls.SECTION_NAME}")
        with Session() as session:
            items = session.query(Property.key, Property.value)\
                           .filter(Property.section == cls.SECTION_NAME)
            return {item.key: item.value for item in iter(items)}


class PropertyObject:
    def __init__(self, section: str, key: str):
        self.section = section
        self.key = key

    def get(self, default: Optional[str] = None) -> Optional[str]:
        with Session() as session:
            item = session.get(Property, (self.section, self.key))
            if item is None:
                ret = default
            else:
                ret = str(item.value)
            logger.debug(f"get section {self.section} key {self.key} => {ret}")
            return ret

    def set(self, value: Optional[str]) -> None:
        """
        Setting value to None is equivalent to unset
        """
        if value is None:
            self.unset()
            return
        logger.debug(f"set section {self.section} key {self.key} to {value}")
        with Session() as session:
            # https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-insert-on-conflict
            stmt = insert(Property)\
                .values(section=self.section, key=self.key, value=value)\
                .on_conflict_do_update(constraint='properties_pkey',
                                       set_={'value': value})
            session.execute(stmt)
            session.commit()

    def unset(self) -> None:
        logger.debug(f"unset section {self.section} key {self.key}")
        with Session() as session:
            # XXX get w/ lock?
            item = session.get(Property, (self.section, self.key))
            if item:
                session.delete(item)
                session.commit()


class UpdateFeeds(Section):
    """properties for UPDATE_FEEDS Section"""
    SECTION_NAME = 'update_feeds'

    modified_since = PropertyObject(SECTION_NAME, "modified_since")
    next_url = PropertyObject(SECTION_NAME, "next_url")


def test() -> None:
    class Test(Section):
        SECTION_NAME = 'test'
        foo = PropertyObject(SECTION_NAME, 'foo')
        mary = PropertyObject(SECTION_NAME, 'mary')

    def clear() -> None:
        Test.foo.unset()
        Test.mary.unset()

    clear()
    all = Test.get_all()
    assert len(all) == 0

    assert Test.foo.get() is None
    assert Test.foo.get('nothing') == 'nothing'

    Test.foo.set('bar')
    assert Test.foo.get() == 'bar'

    Test.foo.set('baz')
    assert Test.foo.get() == 'baz'

    all = Test.get_all()
    assert len(all) == 1 and all[Test.foo.key] == 'baz'

    Test.mary.set('lamb')
    all = Test.get_all()
    assert len(all) == 2 \
        and all[Test.foo.key] == 'baz'\
        and all[Test.mary.key] == 'lamb'

    clear()
    all = Test.get_all()
    assert len(all) == 0
    print("PASSED!")


if __name__ == '__main__':
    import sys

    def usage() -> NoReturn:
        print("'test', 'get property' or 'set property value'")
        sys.exit(1)

    if len(sys.argv) > 1:
        if sys.argv[1] in ('get', 'set'):
            if sys.argv[2] == 'last_update':
                p = UpdateFeeds.modified_since
            else:
                print(f"unknown property {sys.argv[2]}")
            if sys.argv[1] == 'get':
                print(p.get())
            else:
                p.set(sys.argv[3])
        elif sys.argv[1] == 'test':
            test()
        else:
            usage()
    else:
        usage()
