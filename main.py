from flask import Flask
import flask.cli
import logging
from flask import request
import os
import hashlib
import pyperclip
import time 
import requests
from threading import Lock
import threading
import sys

# Disable Flask banner
cli = sys.modules['flask.cli']
cli.show_server_banner = lambda *x: None

app = Flask(__name__)

# Disable flask logging info
log = logging.getLogger('werkzeug')
log.disabled = True

def hash_clip(data: str) -> str:
    '''
    Hash a clipboard entry.

    Args:
        data (str): Clipboard data to hash.

    Returns:
        str: SHA256 hex digest of data.
    '''
    return hashlib.sha256(data.encode()).hexdigest()

last_hash = None
lock = Lock()

@app.route('/clipboard/', methods=['POST'])
def listen():
    # Check for authentication
    token = request.headers.get('XAuth')
    truth = os.getenv('P2PC_TOKEN')
    if token != truth:
        return 'Invalid token', 403
    
    # Clipboard deduplication
    global last_hash
    text = request.form.get('text')
    if not text:
        return 'No text provided', 400
    incoming_hash = hash_clip(data=text)
    if last_hash is not None and incoming_hash == last_hash:
        return 'Duplicate hash', 200
    
    # Copy clipboard data
    pyperclip.copy(text)
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
    text = pyperclip.paste()
    last_hash = hash_clip(text)

    # Exponential back off
    connection_attempts = 0

    while True:
        # Clipbaord deduplication
        text = pyperclip.paste()
        clip_hash = hash_clip(data=text)
        if last_hash is None or clip_hash != last_hash:
            try:
                # Send the clipboard data to the remote server
                r = requests.post(f'http://{remote_ip}:{remote_port}/clipboard/', headers={
                    'XAuth': os.getenv('P2PC_TOKEN'),
                }, data={
                    'text': text,
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
                time.sleep(max(connection_attempts * 3, 15))
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