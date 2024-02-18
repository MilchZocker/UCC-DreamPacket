from flask import Flask, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import cv2
import os
import base64
import requests
import logging
import hashlib
from time import time, gmtime, strftime

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

DATA_DIR = 'data/'
IMAGE_PATH = 'data/images/'
DEFAULT_IMAGE = 'image.png'
VIDEO_PATH = 'canvas.mp4'

IMAGE_SIZE = 1024

# a value of < 1 disables the cooldown
COOLDOWN_IN_SECONDS = 1


def parse_instruction(instruction):
  mode = instruction[0]
  params = instruction[1:]
  if mode == 'g':
      return ('g', None)
  elif mode == 'w' and len(params) == 1:
    return ('w', params)
    
  return (None, None)


def get_user_data_path(ip_hash):
  return f"{DATA_DIR}{ip_hash}.txt"


def get_sentence_and_age(ip_hash):
  path = get_user_data_path(ip_hash)
  if not os.path.exists(path):
    # defaults to 0 seconds since epoch (which doesn't really make sense, but should always allow for placement)
    return ('', 0)
  
  with open(path, "r", encoding="utf-8") as f:
    data = f.read().split(';')
    return (data[0], float(data[1]) if 1 < len(data) else 0)
  
def handle_letter(sentence, letter):
  if letter == '-':
    return sentence[:-1] if len(sentence) > 0 else ''
  if letter == '!':
    return ''
  elif letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ,':
    return sentence + letter
  else:
    return sentence


def set_sentence_data(ip_hash, **kwargs):
  sentence, age = get_sentence_and_age(ip_hash)
  if 'letter' in kwargs:
    sentence = handle_letter(sentence, kwargs['letter'])
  if 'age' in kwargs:
    age = kwargs['age']

  with open(get_user_data_path(ip_hash), "w+", encoding="utf-8") as f:
    f.write(f"{sentence};{age}")
  
  return (sentence, age)


def create_video(image_path=DEFAULT_IMAGE):
  logging.debug('CREATING VIDEO')
  
  logging.debug('image_path %s', image_path)
  
  video_size = IMAGE_SIZE
  video = cv2.VideoWriter(VIDEO_PATH, cv2.VideoWriter_fourcc(*'mp4v'), 1, (video_size, video_size))
  image = cv2.imread(image_path)
  image = cv2.resize(image, (video_size, video_size), interpolation = cv2.INTER_NEAREST)
  video.write(image)

  cv2.destroyAllWindows()
  video.release()


def can_generate_image(age):
  time_elapsed = time() - age
  return COOLDOWN_IN_SECONDS < time_elapsed


def generate_image_from_dreamstudio(sentence):
  url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
  api_key = os.getenv('API_AUTH_KEY')

  body = {
    "steps": 40,
    "width": IMAGE_SIZE,
    "height": IMAGE_SIZE,
    "seed": 0,
    "cfg_scale": 5,
    "samples": 1,
    "text_prompts": [
      {
        "text": sentence,
        "weight": 1
      }
    ],
  }

  headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
  }

  response = requests.post(
    url,
    headers=headers,
    json=body,
  )
  
  logging.debug('POSTED')

  if response.status_code != 200:
    return DEFAULT_IMAGE

  logging.debug('WORKED')

  data = response.json()
  
  for i, image in enumerate(data["artifacts"]):
    with open(f'{IMAGE_PATH}/txt2img_{image["seed"]}.png', "wb") as f:
      f.write(base64.b64decode(image["base64"]))
    return f'{IMAGE_PATH}/txt2img_{image["seed"]}.png'


@app.route('/dream/image/<name>')
def get_image(name):
  create_video(f'{IMAGE_PATH}{name}')
  return send_file(VIDEO_PATH, mimetype='video/mp4')

@app.route('/dream/<instruction>')
def video(instruction):
  ip_hash = hashlib.md5(request.remote_addr.encode('utf-8')).hexdigest()

  mode, data = parse_instruction(instruction)
  logging.debug('%s - %s', mode, data)
  if mode == 'w' and data is None:
    return send_file(VIDEO_PATH, mimetype='video/mp4')
  
  if mode == 'w':
    sentence, age = get_sentence_and_age(ip_hash)
    if not can_generate_image(age):
      return send_file(VIDEO_PATH, mimetype='video/mp4')
    
    sentence, age = set_sentence_data(ip_hash, letter = data)
    image = Image.new('RGB', (IMAGE_SIZE, IMAGE_SIZE), "black")
    I1 = ImageDraw.Draw(image)
    
    font = ImageFont.truetype("arial.ttf", 64)
    
    I1.text((1, 1), sentence, font=font, fill=(255, 255, 255))
    image.save(DEFAULT_IMAGE)
    create_video(DEFAULT_IMAGE)
    set_sentence_data(ip_hash, age = time())
  elif mode == 'g':
    # TODO
    sentence, age = get_sentence_and_age(ip_hash)
    if not can_generate_image(age):
      return send_file(VIDEO_PATH, mimetype='video/mp4')
    
    logging.debug('HELLO %s - %s', sentence, age)
    
    image_path = generate_image_from_dreamstudio(sentence)

    create_video(image_path)
    set_sentence_data(ip_hash, age = time())

  return send_file(VIDEO_PATH, mimetype='video/mp4')

@app.route('/dream')
def get_video():
  return send_file(VIDEO_PATH, mimetype='video/mp4')

if __name__ == "__main__":
  if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
  if not os.path.exists(IMAGE_PATH):
    os.makedirs(IMAGE_PATH)
  if not os.path.exists(DEFAULT_IMAGE):
    image = Image.new('RGB', (IMAGE_SIZE, IMAGE_SIZE), "black")
    image.save(DEFAULT_IMAGE)
  if not os.path.exists(VIDEO_PATH):
    create_video()
  logging.basicConfig(level=logging.INFO, filename='app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
  app.run(host='0.0.0.0', port=5000)
