#!/bin/sh

# run unix-domain syslog socket listener,
# writes single log file for all containers/processes.
# expects SYSLOG_PATH and LOG_DIR to be set:
python -m mc_logging.sink
