# Dead simple text-to-speech (TTS) with piper

Need: Generate audio quickly from text
Details: Finnish & English, playable through WebUI
NOTES: Tested on Ubuntu LTS 22.04

## Design

Audio converter port range starts from 5500 and goes up.
5500 Portal
5501 English
5502 Finnish

## Implementation

Python, nginx, systemd.

piper_wrapper.sh starts all the python programs. It assums the `$piper_dir` to 
contain python virtual env and loads it + applications.

there is a systemd package to start the entire set nicely.

## configuration / installation

There is the python side to configure and then OS and HTTP server

### python part
```bash
python3 -m venv /srv/piper
source /srv/piper/bin/activate
pip3 install -r requirements.txt
```

#### dirrrty hack
The package seems to be missing the HTTP server...
```bash
wget https://raw.githubusercontent.com/rhasspy/piper/master/src/python_run/piper/http_server.py -O /srv/piper/lib64/python3.10/site-packages/piper/http_server.py
```

### service side
copy files to `/srv/piper`
- app.py
- templates/index.html
- piper_wrapper.sh

Create a service user to limit possible damage
```bash
sudo adduser -m piper
sudo chown -R piper:piper /srv/piper
```

enable systemd service
```bash
sudo systemctl enable piper.service
```

enable nginx configuration by copying text-to-speech to `/etc/nginx/sites-enabled`
```bash
sudo systemctl restart nginx
```

## run time

Browser to http://ollama.intra.leivo/tts

## References

https://github.com/rhasspy/piper