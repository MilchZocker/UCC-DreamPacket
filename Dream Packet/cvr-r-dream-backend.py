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
from pathlib import Path
from time import time
from collections import defaultdict

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
root_path = Path(__file__).parent.resolve().as_posix()

DATA_DIR = root_path + 'app/data/'
IMAGE_PATH = root_path + 'app/data/images/'
DEFAULT_IMAGE = root_path + 'app/empty.png'
WORKING_IMAGE = root_path + 'app/image.png'
VIDEO_BASE_PATH = root_path + 'app/canvas'
VIDEO_EXTENSION = '.mp4'
GLOBAL_VIDEO_PATH = VIDEO_BASE_PATH + VIDEO_EXTENSION
DEFAULT_VIDEO_PATH = root_path + 'app/empty' + VIDEO_EXTENSION
API_KEY_ENVIRONMENT_VARIABLE = 'API_AUTH_KEY'

IMAGE_SIZE = 1024

# a value of < 1 disables the cooldown
COOLDOWN_IN_SECONDS = 0.4

# Track last inputs per user
last_inputs = defaultdict(lambda: {'letter': None, 'time': 0})


def get_video_path(channel):
  if channel is None:
    return GLOBAL_VIDEO_PATH
  return VIDEO_BASE_PATH + str(channel) + VIDEO_EXTENSION

def parse_instruction(instruction):
  mode = instruction[0]
  params = instruction[1:]
  if mode == 'g':
      return ('g', None)
  elif mode == 'w' and len(params) == 1:
    return ('w', params)
  elif mode == 'c':
    return ('c', int(params))
    
  return (None, None)


def get_user_data_path(ip_hash):
  return f"{DATA_DIR}{ip_hash}.txt"


def get_sentence_data(ip_hash):
  path = get_user_data_path(ip_hash)
  if not os.path.exists(path):
    # defaults to 0 seconds since epoch (which doesn't really make sense, but should always allow for placement)
    return ('', 0, None)
  
  with open(path, "r", encoding="utf-8") as f:
    data = f.read().split(';')
    return (data[0], float(data[1]) if 1 < len(data) else 0, int(data[2]) if 2 < len(data) else None)
  
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
  sentence, age, channel = get_sentence_data(ip_hash)
  if 'letter' in kwargs:
    sentence = handle_letter(sentence, kwargs['letter'])
  if 'age' in kwargs:
    age = kwargs['age']
  if 'channel' in kwargs:
    channel = kwargs['channel']
    logging.debug('Got a channel')

  data = [sentence, str(age)]
  if channel is not None:
    data = data + [str(channel)]

  logging.debug(';'.join(data))

  with open(get_user_data_path(ip_hash), "w+", encoding="utf-8") as f:
    f.write(';'.join(data))
  
  return (sentence, age, channel)


def create_video(image_path = DEFAULT_IMAGE, video_path = GLOBAL_VIDEO_PATH):
  logging.debug('CREATING VIDEO')
  logging.debug('image_path %s', image_path)
  
  video_size = IMAGE_SIZE
  video = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'mp4v'), 1, (video_size, video_size))
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
  api_key = os.getenv(API_KEY_ENVIRONMENT_VARIABLE)

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
    return None

  logging.debug('WORKED')

  data = response.json()
  
  for i, image in enumerate(data["artifacts"]):
    with open(f'{IMAGE_PATH}/txt2img_{image["seed"]}.png', "wb") as f:
      f.write(base64.b64decode(image["base64"]))
    return f'{IMAGE_PATH}/txt2img_{image["seed"]}.png'
  
def get_ip_hash():
  return hashlib.md5(request.remote_addr.encode('utf-8')).hexdigest()

def get_video(channel):
  video_path = get_video_path(channel)
  if os.path.exists(video_path):
    return send_file(video_path, mimetype='video/mp4')
  return send_file(DEFAULT_VIDEO_PATH, mimetype='video/mp4')


@app.route('/dream/image/<name>')
def get_image(name):
    ip_hash = get_ip_hash()
    _, _, channel = get_sentence_data(ip_hash)
    create_video(f'{IMAGE_PATH}{name}')
    return get_video(channel)


@app.route('/dream/<instruction>')
def video(instruction):
    ip_hash = get_ip_hash()

    mode, data = parse_instruction(instruction)
    logging.debug('%s - %s', mode, data)

    sentence, age, channel = get_sentence_data(ip_hash)

    if mode == 'w':
        if data is None:
            return get_video(channel)

        # Check if this is a repeated input within cooldown
        current_time = time()
        user_last_input = last_inputs[ip_hash]
        
        if (data == user_last_input['letter'] and 
            current_time - user_last_input['time'] < COOLDOWN_IN_SECONDS):
            # Ignore repeated input during cooldown but keep existing text
            return get_video(channel)
        
        # Update last input data
        last_inputs[ip_hash] = {
            'letter': data,
            'time': current_time
        }
        
        # Process the input normally
        sentence, age, channel = set_sentence_data(ip_hash, letter=data, age=current_time)
        image = Image.new('RGB', (IMAGE_SIZE, IMAGE_SIZE), "black")
        I1 = ImageDraw.Draw(image)
        
        font = ImageFont.truetype("arial.ttf", 64)
        
        I1.text((1, 1), sentence, font=font, fill=(255, 255, 255))
        image.save(WORKING_IMAGE)
        create_video(WORKING_IMAGE, get_video_path(channel))
        
        return get_video(channel)
    elif mode == 'g':
        if not can_generate_image(age):
            return get_video(channel)
        
        logging.debug('HELLO %s - %s', sentence, age)
        
        image_path = generate_image_from_dreamstudio(sentence)
        if image_path is not None:
            create_video(image_path, get_video_path(channel))
            set_sentence_data(ip_hash, age = time())
    elif mode == 'c':
        set_sentence_data(ip_hash, channel = data)

    return get_video(channel)

@app.route('/dream')
def default_route():
  ip_hash = get_ip_hash()
  _, _, channel = get_sentence_data(ip_hash)
  return get_video(channel)

if __name__ == "__main__":
  if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
  if not os.path.exists(IMAGE_PATH):
    os.makedirs(IMAGE_PATH)
  image = Image.new('RGB', (IMAGE_SIZE, IMAGE_SIZE), "black")
  image.save(DEFAULT_IMAGE)
  if not os.path.exists(DEFAULT_VIDEO_PATH):
    create_video(DEFAULT_IMAGE, DEFAULT_VIDEO_PATH)
  logging.basicConfig(level=logging.INFO, filename='app.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')
  app.run(host='0.0.0.0', port=5000)