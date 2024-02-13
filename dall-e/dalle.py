from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

image_request = input("What kind of image you want? ")

response = client.images.generate(
  model="dall-e-3",
  prompt=image_request,
  size="1024x1024",
  quality="standard",
  n=1,
)

image_url = response.data[0].url

print(image_url)
