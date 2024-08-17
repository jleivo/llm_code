#!/bin/bash

piper_dir='/srv/piper'
# Following shellchecks are disabled as due to the for loop logic, shellcheck
# can't see the variables being used.
# shellcheck disable=SC2034
port_fi='5502'
# shellcheck disable=SC2034
model_fi='fi_FI-harri-medium.onnx'
# shellcheck disable=SC2034
port_en='5501'
# shellcheck disable=SC2034
model_en='en_GB-cori-high.onnx'

cd "$piper_dir" || exit 1

for lang in en 'fi'; do
  port=port_$lang
  model=model_$lang
# shellcheck disable=SC1091
  source "$piper_dir/bin/activate" && python3 -m piper.http_server \
  --data-dir "$piper_dir" --model ${!model} --port ${!port} &
done

# Start final web portal
# shellcheck disable=SC1091
source "$piper_dir/bin/activate" && python3 "$piper_dir/app.py"
