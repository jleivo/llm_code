import requests
import json
import io
import base64
from PIL import Image

stable_diffusion_server = "https://stablediffusion.intra.leivo"

message_template = {
  "prompt": "",
  "negative_prompt": "",
  "seed": -1,
  "subseed": -1,
  "subseed_strength": 0,
  "seed_resize_from_h": -1,
  "seed_resize_from_w": -1,
  "sampler_name": "Euler a",
  "batch_size": 1,
  "n_iter": 1,
  "steps": 30,
  "cfg_scale": 6.5,
  "width": 512,
  "height": 512,
  "restore_faces": True,
  "tiling": True,
  "do_not_save_samples": False,
  "do_not_save_grid": False,
  "eta": 0,
  "denoising_strength": 0,
  "s_min_uncond": 0,
  "s_churn": 0,
  "s_tmax": 0,
  "s_tmin": 0,
  "s_noise": 0,
  "override_settings": {},
  "override_settings_restore_afterwards": True,
  "refiner_switch_at": 0,
  "disable_extra_networks": False,
  "comments": {},
  "enable_hr": False,
  "firstphase_width": 0,
  "firstphase_height": 0,
  "hr_second_pass_steps": 0,
  "hr_resize_x": 0,
  "hr_resize_y": 0,
  "hr_prompt": "",
  "hr_negative_prompt": "",
  "sampler_index": "Euler a",
  "script_args": [],
  "send_images": True,
  "save_images": False,
  "alwayson_scripts": {}
}

## send a JSON message to server URL

def request_picture(user_message):

    # Convert the dictionary to a JSON string
    json_string = json.dumps(message_template)
    # Modify the JSON string as needed
    json_string = json_string.replace('"prompt": ""', '"prompt": "'+ user_message + '"')
    headers = {"Content-Type": "application/json"}
    full_URL = stable_diffusion_server + "/" "sdapi/v1/txt2img"
    response = requests.post(full_URL, headers=headers, data=json_string, verify=False)
    
    # work out the image from the response
    data = response.json()
    image = Image.open(io.BytesIO(base64.b64decode(data['images'][0])))

    ### Issue! With this code the API works once, then you get CUDA out of memory errors...


if __name__ == '__main__':
    # request_picture("test")
    message = input("What kind of picture you want? ")
    request_picture(message)
