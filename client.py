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
            new_hash = packet.get('hash')
            datatype = packet.get('datatype')
            data = packet.get('data')

            # If null data, ignore message
            if not origin or not new_hash or not datatype or not data:
                continue

            # If origin = this machine, ignore message
            if origin == client_id:
                continue

            if datatype == 'image':
                # Parse image from packet
                data = http_to_image(data)
            elif datatype == 'text':
                pass
            else:
                continue

            # Deduplicate data
            async with lock:
                if new_hash and last_hash and new_hash == last_hash:
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
    global lock
    
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
            async with lock:
                if last_hash is not None and clip_hash == last_hash:
                    await asyncio.sleep(0.5)
                    continue

            await conn.send(json.dumps({
                'XAuth': token,
                'origin': client_id,
                'hash': clip_hash,
                'datatype': datatype,
                'data': data,
            }))

            async with lock:
                last_hash = clip_hash

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