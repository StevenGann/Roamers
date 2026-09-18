#!/bin/bash
# Start roamerd fully detached from the SSH session.
cd /opt/roamers
exec ./.venv/bin/python -m roamerd >/tmp/roamerd-run.log 2>&1
