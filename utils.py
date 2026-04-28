import hashlib
import io
import base64

from PIL import Image

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
    img = img.convert('RGB')
    img.thumbnail((1920, 1080))
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