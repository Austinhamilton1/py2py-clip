import asyncio
import sys
import json
import os

from websockets.asyncio.server import serve
from asyncio.locks import Lock

from utils import *

last_hash = None
hash_lock = Lock()
clients = set()
client_lock = Lock()

async def listen(conn):
    '''Listen for incoming connections and manage them'''
    global last_hash
    # Update the client lookup (keyed by client UUID)
    async with client_lock:
        clients.add(conn)

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
            raw_data = packet.get('data')

            # If null data, ignore message
            if not origin or not new_hash or not datatype or not raw_data:
                continue 

            should_broadcast = False

            async with hash_lock:
                if new_hash != last_hash:
                    last_hash = new_hash
                    should_broadcast = True

            if not should_broadcast:
                continue

            # Send data to all clients
            conns = []
            async with client_lock:
                conns = list(clients)
            
            dead = []
            for ws in conns:
                if ws is conn:
                    continue
                try:
                    await ws.send(json.dumps({
                        'XAuth': truth,
                        'origin': origin,
                        'hash': new_hash,
                        'datatype': datatype,
                        'data': raw_data,
                    }))
                except:
                    dead.append(ws)

            async with client_lock:
                for ws in dead:
                    clients.remove(ws)

    except Exception:
        pass

    return conn
        

async def handler(conn):
    origin = None
    try:
        origin = await listen(conn)
    except asyncio.CancelledError:
        pass
    finally:
        if origin:
            async with client_lock:
                clients.remove(origin)
            
async def server(port: int):
    '''
    Initializes the server and dispatches tasks.

    Args:
        port (int): Port to listen on.
    '''
    try:
        async with serve(handler, '0.0.0.0', port, close_timeout=None) as server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} [port number]')
        exit()

    port = int(sys.argv[1])

    try:
        asyncio.run(server(port))
    except KeyboardInterrupt:
        pass