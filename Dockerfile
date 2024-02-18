FROM python:3.9-slim-buster

# Install required fonts
RUN sed -i'.bak' 's/$/ contrib/' /etc/apt/sources.list
RUN apt-get update && apt-get install -y ttf-mscorefonts-installer fontconfig

# Nessesary for cv2
RUN apt-get install -y libsm6 libxext6 ffmpeg libfontconfig1 libxrender1 libgl1-mesa-glx

# Copy repository content to container
WORKDIR "/debian/Desktop/UCC-DreamPacket/Dream Packet"
COPY ["./Dream Packet/", "./"]

# Begin setup for Python
RUN pip install -r requirements.txt

EXPOSE 5000

# Lauch Dream Packet
CMD python cvr-r-dream-backend.py
