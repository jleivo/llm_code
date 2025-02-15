#!/bin/bash
#
# 2024-11-26 12:56
# Really quick and dirty upgrade procedure

sudo -u piper /bin/bash -c "source /srv/piper/bin/activate; pip install --upgrade piper"
