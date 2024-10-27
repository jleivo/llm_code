#!/bin/bash
#
# Script to start discord bot

BASEDIR='/srv/discord_bot'
LOGFILE='/var/log/discord_bot.log'

. "$BASEDIR/lunatic_model/bin/activate"
cd "$BASEDIR" || { echo "Could not go to base dir"; return 1; }
python3 "$BASEDIR/discord_bot.py" >> "$LOGFILE" 2>&1
