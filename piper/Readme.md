# Text to speech page

Dead simple page to create speech from text. Uses piper as the TTS engine
ref: https://github.com/rhasspy/piper

Simple page which allows you to post text, play the result and download if you
so choose.

## Design

Audio converter port range starts from 5500 and goes up.
5500 Portal
5501 English
5502 Finnish

## Implementation

piper_wrapper.sh starts all the python programs. It assums the `$piper_dir` to 
contain python virtual env and loads it + applications.

there is a systemd package to start the entire set nicely.

## Installation

**enable python**
python3 -m venv /srv/piper
source /srv/piper/bin/activate
pip -r requirements.txt

**copy application**
copy 
- app.py
- templates/index.html
- piper_wrapper.sh
to /srv/piper

enable piper.service in systemd
add text-to-speech to nginx sites-enabled and restart