# Rückwärtskompatibilität für bestehende Tests und Importe.
from app.services.media_storage import MediaStorage


class ImageStorage(MediaStorage):
    pass
