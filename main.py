from flask import Flask
import flask.cli
import logging
from flask import request
import io
import base64
from PIL import Image, ImageGrab
import os
import hashlib
import pyperclip
import pyperclipimg
import time 
import requests
from threading import Lock
import threading
import sys

# Disable Flask banner
# cli = sys.modules['flask.cli']
# cli.show_server_banner = lambda *x: None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Disable flask logging info
# log = logging.getLogger('werkzeug')
# log.disabled = True

def hash_clip(datatype: str, data: any) -> str:
    '''
    Hash a clipboard entry.

    Args:
        datatype (str): 'image' | 'text'
        data (any): Clipboard data to hash.

    Returns:
        str: SHA256 hex digest of data.
    '''
    if datatype == 'image':
        return hashlib.sha256(data).hexdigest()
    elif datatype == 'text':
        return hashlib.sha256(data.encode()).hexdigest()
    
    raise ValueError(f"Data type must be 'image' or 'text' not '{datatype}'")

def image_to_bytes(img: Image.Image) -> bytes:
    '''
    Convert an image to a byte array.

    Args:
        img (Image.Image): Image to convert.
    Returns:
        bytes: Raw bytes of the image
    '''
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return buf.getvalue()

def bytes_to_http(img_bytes: bytes) -> str:
    '''
    Convert an image to base64 encoded string
    object for serialization over network.

    Args:
        img_bytes (bytes): Image to serialize.
    Returns:
        str - Base64 encoded string of bytes
    '''
    return base64.b64encode(img_bytes).decode()

def http_to_image(img_str: str) -> Image.Image:
    '''
    Convert a base64 encoded string object to
    image for deserialization over network.

    Args:
        img_str (str): Base64 encoded image string.
    Returns:
        Image.Image - Deserialized image.
    '''
    raw = base64.b64decode(img_str)
    return Image.open(io.BytesIO(raw))

last_hash = None
lock = Lock()

@app.route('/clipboard/', methods=['POST'])
def listen():
    # Check for authentication
    token = request.headers.get('XAuth')
    truth = os.getenv('P2PC_TOKEN')
    if token != truth:
        return 'Invalid token', 403
    
    # Receive incoming dadta
    global last_hash
    datatype = request.json.get('type')
    data = request.json.get('data')
    if not datatype or not data:
        return 'Invalid data request', 400
    
    # Data decoding
    if datatype == 'image':
        img = http_to_image(data)
        incoming_hash = hash_clip('image', image_to_bytes(img))
    elif datatype == 'text':
        img = None
        incoming_hash = hash_clip('text', data)
    else:
        return f"Invalid data type '{datatype}'", 400
    
    # Data deduplication
    if last_hash is not None and incoming_hash == last_hash:
        return 'Duplicate hash', 200
    
    # Copy clipboard data
    if img:
        pyperclipimg.copy(img)
    else:
        pyperclip.copy(data)
    
    # Update hash
    with lock:
        last_hash = incoming_hash
    
    return 'Successful copy', 200

def client(remote_ip: str, remote_port: int) -> None:
    '''
    Client loop.

    Args:
        remote_ip (str): Remote server listening for clipboard data.
        remote_port (int): Remote server listening port

    Returns:
        None
    '''
    # Initialize clipboard hash to account for current clipboard
    global last_hash
    MAX_SIZE = (1920, 1080)
    img = ImageGrab.grabclipboard()
    if img:
        img.thumbnail(MAX_SIZE)
        buf = image_to_bytes(img)
        data = bytes_to_http(buf)
        datatype = 'image'
        last_hash = hash_clip(datatype, buf)
    else:
        data = pyperclip.paste()
        datatype = 'text'
        last_hash = hash_clip(datatype, data)

    # Exponential back off
    connection_attempts = 0

    while True:
        # Grab clipboard data
        img = ImageGrab.grabclipboard()
        if img:
            img.thumbnail(MAX_SIZE)
            buf = image_to_bytes(img)
            data = bytes_to_http(buf)
            datatype = 'image'
            clip_hash = hash_clip(datatype, buf)
        else:
            data = pyperclip.paste()
            datatype = 'text'
            clip_hash = hash_clip(datatype, data)

        # Data deduplication
        if last_hash is None or clip_hash != last_hash:
            try:
                # Send the clipboard data to the remote server
                r = requests.post(f'http://{remote_ip}:{remote_port}/clipboard/', headers={
                    'XAuth': os.getenv('P2PC_TOKEN'),
                }, json={
                    'type': datatype,
                    'data': data,
                }, timeout=3)

                if r.status_code == 200:
                    connection_attempts = 0
                    with lock:
                        last_hash = clip_hash
                elif r.status_code != 200:
                    print('Server returned status code', r.status_code)
                    break
            except requests.exceptions.Timeout:
                connection_attempts += 1
                # Sleep for a maximum of 15 seconds between retries
                time.sleep(min(connection_attempts * 3, 15))
                continue
            
        time.sleep(0.5)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} [remote ip] [remote port]')
        exit()

    remote_ip = sys.argv[1]
    remote_port = sys.argv[2]
    threading.Thread(target=client, args=(remote_ip, remote_port), daemon=True).start()
    app.run(host='0.0.0.0', port=remote_port)