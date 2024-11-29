import io
import base64
from PIL import Image

with open('image.json','r') as file:
  
  base64_string = file.read()
  decoded_image_bytes = base64.b64decode(base64_string)


  image = Image.open(io.BytesIO(decoded_image_bytes))
  original_format = "png"
  image.save(f"output.{original_format.lower()}", format=original_format)
