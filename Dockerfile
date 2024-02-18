	FROM python:3.13.0a3-bookworm

	# Updating system packages
	RUN apt-get update
	RUN apt-get upgrade -y
	
	# Nessesary for cv2
	RUN apt-get install -y libgl1-mesa-glx

	# Set ENV for Repository extract
	RUN mkdir /app
	WORKDIR /dreampacket
	COPY ["./Dream Packet/", "./"]
	
	# Begin setup for Python
	RUN pip install --upgrade pip
	RUN pip install Pillow Flask opencv-python Werkzeug requests
	
	# Launch Dream Packet
	CMD python /dreampacket/cvr-r-dream-backend.py
