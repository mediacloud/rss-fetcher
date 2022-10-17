"""
paths/dirs for rss-fetcher
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')

# call check_dir (below) before using!
LOG_DIR = os.path.join(STORAGE_DIR, 'logs')
INPUT_RSS_DIR = os.path.join(STORAGE_DIR, 'rss-input-files')
OUTPUT_RSS_DIR = os.path.join(STORAGE_DIR, 'rss-output-files')


def check_dir(dir: str):
    """
    call before trying to create files in a directory
    """
    # XXX error if exists and not a dir (symlink to dir is ok)
    if not os.path.exists(dir):
        os.makedirs(dir, exist_ok=True)
