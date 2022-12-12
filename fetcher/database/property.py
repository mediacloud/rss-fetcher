
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError # TEMP

from fetcher.database import Session
from fetcher.database.models import Property

class Section(Enum):
    UPDATE_FEEDS = 'update_feeds'

class UpdateFeeds(Enum):
    """UPDATE_FEEDS section keys"""
    MODIFIED_SINCE = 'modified_since'

def get(section: str,
        key: str,
        default:Optional[str] = None) -> Optional[str]:
    with Session() as session:
        stmt = select(Property).where(Property.section == section,
                                      Property.key == key)
        item = session.scalar(stmt)
        if item is None:
            return default
        return item.value

def get_all(section: str) -> Dict[str, str]:
    """
    return a dict with all key/values in a section
    """
    with Session() as session:
        stmt = select(Property).where(Property.section == section)
        return {item.key: item.value for item in session.scalars(stmt)}

def set(section: str,
                 key: str,
                 value :Optional[str]) -> None:
    with Session() as session:
        # https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-insert-on-conflict
        stmt = insert(Property)\
            .values(section=section, key=key, value=value)\
            .on_conflict_do_update(constraint='properties_pkey',
                                   set_={'value': value})
        session.execute(stmt)
        session.commit()

def unset(section: str, key: str) -> None:
    with Session() as session:
        stmt = delete(Property).where(Property.section == section,
                                      Property.key == key)
        session.execute(stmt)
        session.commit()


if __name__ == '__main__':
    def clear():
        unset('foo', 'bar')
        unset('foo', 'mary')

    clear()
    all = get_all('foo')
    assert len(all) == 0

    assert get('foo', 'bar') is None
    assert get('foo', 'bar', 'nothing') == 'nothing'
    set('foo', 'bar', 'baz')
    assert get('foo', 'bar') == 'baz'

    all = get_all('foo')
    assert len(all) == 1 and all['bar'] == 'baz'

    set('foo', 'mary', 'lamb')
    all = get_all('foo')
    assert len(all) == 2 and all['bar'] == 'baz' and all['mary'] == 'lamb'
    print("PASSED!")
    clear()
    all = get_all('foo')
    assert len(all) == 0
