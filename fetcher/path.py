"""
paths/dirs for rss-fetcher
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mount point for stable storage.
# if a script is going to create multiple files,
# please consider creating a subdir (like the ones below)
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')

# call check_dir (below) before using!
LOG_DIR = os.path.join(STORAGE_DIR, 'logs')
INPUT_RSS_DIR = os.path.join(STORAGE_DIR, 'saved-input-files')
OUTPUT_RSS_DIR = os.path.join(STORAGE_DIR, 'rss-output-files')
DB_ARCHIVE_DIR = os.path.join(STORAGE_DIR, 'db-archive')
LOCK_DIR = os.path.join(STORAGE_DIR, 'lock')


def check_dir(dir: str) -> None:
    """
    call before trying to create files in a directory
    """
    # XXX error if exists and not a dir (symlink to dir is ok)
    #  check first and try removing??
    if not os.path.exists(dir):
        os.makedirs(dir, exist_ok=True)
