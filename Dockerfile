	FROM python:3.13.0a3-bookworm

	# Updating system packages
	RUN apt-get update
	RUN apt-get upgrade
	
	# Nessesary for cv2
	RUN apt-get install -y libgl1-mesa-glx

	# Get git to get good
	RUN apt-get install git -y

	# Set ENV for Repository extract
	WORKDIR "/debian/Desktop"
	RUN git clone https://github.com/MilchZocker/UCC-DreamPacket --progress
	
	# Move to Repository directory
	WORKDIR "/debian/Desktop/UCC-DreamPacket/Dream Packet"

	# Begin setup for Python
	RUN pip install --upgrade pip
	RUN pip install Pillow Flask opencv-python Werkzeug

	# Lauch Dream Packet
	CMD ["python", "cvr-r-dream-backend.py"]
