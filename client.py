import json
import asyncio
import uuid
import pyperclip
import pyperclipimg
import os
import sys

from websockets.asyncio.client import connect
from asyncio.locks import Lock
from PIL import ImageGrab, Image

from utils import *

client_id = uuid.uuid4().hex
last_hash = None
lock = Lock()

async def receiver(conn):
    '''Receives incoming clipboard messages and handles them'''
    global client_id
    global last_hash
    global lock

    try:
        while True:
            # Receive incoming message
            msg = await conn.recv()
            packet = json.loads(msg)

            # Authorize request
            token = packet.get('XAuth')
            truth = os.getenv('P2PC_TOKEN')
            if not truth or token != truth:
                continue

            # Receive message meta data
            origin = packet.get('origin')
            datatype = packet.get('datatype')
            data = packet.get('data')

            # If null data, ignore message
            if not origin or not datatype or not data:
                continue

            # If origin = this machine, ignore message
            if origin == client_id:
                continue

            if datatype == 'image':
                # Parse image from packet
                data = http_to_image(data)
                new_hash = hash_clip('image', image_to_bytes(data))
            elif datatype == 'text':
                new_hash = hash_clip('text', data)
                pass
            else:
                new_hash = None
                continue

            # Deduplicate data
            async with lock:
                if new_hash == last_hash:
                    continue
                last_hash = new_hash

            # Copy data to clipboard
            if datatype == 'image':
                pyperclipimg.copy(data)
            else:
                pyperclip.copy(data)
    except asyncio.CancelledError:
        pass

async def watcher(conn):
    '''Watches local clipboard for changes.'''
    global client_id
    global last_hash

    # Initialize last hash so that current clipboard is not flagged
    async with lock:
        init_img = ImageGrab.grabclipboard()
        if isinstance(init_img, Image.Image):
            init_buf = image_to_bytes(init_img)
            last_hash = hash_clip('image', init_buf)
        else:
            init_data = pyperclip.paste()
            last_hash = hash_clip('text', init_data)
    
    token = os.getenv('P2PC_TOKEN')

    try:
        while True:
            # Grab the current clipboard
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                buf = image_to_bytes(img)
                data = bytes_to_http(buf)
                datatype = 'image'
                clip_hash = hash_clip('image', buf)
            else:
                data = pyperclip.paste()
                datatype = 'text'
                clip_hash = hash_clip('text', data)

            # Data deduplication
            should_send = False
            async with lock:
                if last_hash != clip_hash:
                    should_send = True
                    last_hash = clip_hash

            if should_send:
                await conn.send(json.dumps({
                    'XAuth': token,
                    'origin': client_id,
                    'datatype': datatype,
                    'data': data,
                }))

            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        pass


async def client(remote_ip: str, remote_port: int):
    '''
    Attempts to connect to the server and dispatches tasks.

    Args:
        remote_ip (str): IP address of the remote server.
        remote_port (int): Port of the remote server.
    '''
    while True:
        try:
            async with connect(f'ws://{remote_ip}:{remote_port}', close_timeout=None) as conn:
                # Need a listener and a clipboard watcher
                receiver_task = asyncio.create_task(receiver(conn))
                watcher_task = asyncio.create_task(watcher(conn))
                tasks = [receiver_task, watcher_task]

                # Run the two tasks and close gracefully on exit
                try:
                    await asyncio.gather(*tasks)
                finally:
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} [remote host] [remote port]')
        exit()

    remote_ip = sys.argv[1]
    remote_port = int(sys.argv[2])

    try:
        asyncio.run(client(remote_ip, remote_port))
    except KeyboardInterrupt:
        pass