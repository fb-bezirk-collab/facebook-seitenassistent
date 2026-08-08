from app.media_monitor.fetchers.apa import fetch_apa
from app.media_monitor.fetchers.exxpress import fetch_exxpress
from app.media_monitor.fetchers.heute import fetch_heute
from app.media_monitor.fetchers.kleine import fetch_kleine
from app.media_monitor.fetchers.krone import fetch_krone
from app.media_monitor.fetchers.kurier import fetch_kurier
from app.media_monitor.fetchers.noen import fetch_noen
from app.media_monitor.fetchers.oe24 import fetch_oe24
from app.media_monitor.fetchers.orf import fetch_orf
from app.media_monitor.fetchers.presse import fetch_presse
from app.media_monitor.fetchers.sn import fetch_sn
from app.media_monitor.fetchers.standard import fetch_standard

__all__ = [
    'fetch_apa', 'fetch_exxpress', 'fetch_heute', 'fetch_kleine', 'fetch_krone',
    'fetch_kurier', 'fetch_noen', 'fetch_oe24', 'fetch_orf', 'fetch_presse',
    'fetch_sn', 'fetch_standard',
]
