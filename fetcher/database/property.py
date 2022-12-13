
from enum import Enum
from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from fetcher.database import Session
from fetcher.database.models import Property


class Section(Enum):
    UPDATE_FEEDS = 'update_feeds'
    TEST = 'test'


class UpdateFeeds(Enum):
    """keys for UPDATE_FEEDS Section"""
    MODIFIED_SINCE = 'modified_since'


def get(section: Section,
        key: Enum,
        default: Optional[str] = None) -> Optional[str]:
    with Session() as session:
        item = session.get(Property, (section.value, key.value))
        if item is None:
            return default
        return str(item.value)


def get_all(section: Section) -> Dict[str, str]:
    """
    return a dict with all key/values in a section
    """
    with Session() as session:
        items = session.query(
            Property.key, Property.value).filter(
            Property.section == section.value)
        return {item.key: item.value for item in items}


def set(section: Section, key: Enum, value: Optional[str]) -> None:
    if value is None:
        unset(section, key)
        return

    with Session() as session:
        # https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql-insert-on-conflict
        stmt = insert(Property)\
            .values(section=section.value, key=key.value, value=value)\
            .on_conflict_do_update(constraint='properties_pkey',
                                   set_={'value': value})
        session.execute(stmt)
        session.commit()


def unset(section: Section, key: Enum) -> None:
    with Session() as session:
        item = session.get(Property, (section.value, key.value))
        if item:
            session.delete(item)
            session.commit()


if __name__ == '__main__':
    class TestItem(Enum):
        BAR = 'bar'
        MARY = 'mary'

    def clear() -> None:
        unset(Section.TEST, TestItem.BAR)
        unset(Section.TEST, TestItem.MARY)

    clear()
    all = get_all(Section.TEST)
    assert len(all) == 0

    assert get(Section.TEST, TestItem.BAR) is None
    assert get(Section.TEST, TestItem.BAR, 'nothing') == 'nothing'
    set(Section.TEST, TestItem.BAR, 'baz')
    assert get(Section.TEST, TestItem.BAR) == 'baz'

    all = get_all(Section.TEST)
    assert len(all) == 1 and all[TestItem.BAR.value] == 'baz'

    set(Section.TEST, TestItem.MARY, 'lamb')
    all = get_all(Section.TEST)
    assert len(all) == 2 \
        and all[TestItem.BAR.value] == 'baz'\
        and all[TestItem.MARY.value] == 'lamb'
    print("PASSED!")
    clear()
    all = get_all(Section.TEST)
    assert len(all) == 0
