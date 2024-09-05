from flask import Flask, request
import subprocess

app = Flask(__name__)

@app.route('/api', methods=['GET'])
def process_command():
    cmd = request.args.get('ollama')

    if cmd == 'single':
        if is_single():
            return "Ollama already running in single mode"
        else:
            return start_ollama('single')
    elif cmd == 'all':
        if is_single():
            start_ollama('all')
            return "Ollama started in all GPU mode"
        else:
            return "Ollama already running in all mode"
    else:
        return "Invalid command: Please provide valid 'cmd' parameter (either 'single' or 'all')"

# check the status of ollama container, if the results from shell command
# docker exec ollama printenv does include "NVIDIA_VISIBLE_DEVICES=GPU-0a895c3d-0f7f-46f1-50ab-1f84e96f7083"
# then the container is in single mode

def is_single():

    cmd = 'docker exec ollama printenv'
    output, exit_code = run_bash(cmd)
    if exit_code != 0:
        print("Container not running?! Trying to start in single mode")
        return start_ollama('single')

    if "GPU-0a895c3d-0f7f-46f1-50ab-1f84e96f7083" in output:
        return True
    else:
        return False

def run_bash(command):
    try:
        result = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
        return result.decode('utf-8'), 0
    except subprocess.CalledProcessError as e:
        return e.output.decode('utf-8'), e.returncode

def stop_ollama():
    cmd_stop = 'docker stop ollama && docker container rm ollama'
    output, exit_code = run_bash(cmd_stop)
    return True

# function to start ollama either in single or in all gpu mode
def start_ollama(mode):

    stop_ollama()

    cmd_single = 'docker run -d --gpus=0 -e NVIDIA_VISIBLE_DEVICES=GPU-0a895c3d-0f7f-46f1-50ab-1f84e96f7083,GPU-90689051-9191-c8a4-75b2-ab4e04dae040 -v ollama:/root/.ollama -p 11434:11434 -e OLLAMA_MAX_LOADED_MODELS=4 --name ollama --restart always ollama/ollama'
    cmd_all = 'docker run -d --gpus=all -v ollama:/root/.ollama -p 11434:11434 -e OLLAMA_MAX_LOADED_MODELS=4 --name ollama --restart always ollama/ollama'

    if mode == 'single':
        output, exit_code = run_bash(cmd_single)
        if exit_code != 0:
            return output
        else:
            return "Ollama started in single mode"
    elif mode == 'all':
        output, exit_code = run_bash(cmd_all)
        if exit_code != 0:
            return output
        else:
            return "Ollama started in all mode"
    
    return "Invalid mode"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5080)