"""
asset_cache.py — PolyHaven + texture asset manager.

Downloads PBR assets (HDRIs, textures, 3D models) from PolyHaven via HTTP,
caches locally in assets/polyhaven/. No API key needed (CC0 license).
"""
import os
import json
import logging
import hashlib
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_CACHE_DIR = os.path.join(_PROJECT_ROOT, 'assets', 'polyhaven')
_MANIFEST_PATH = os.path.join(_CACHE_DIR, 'manifest.json')

# PolyHaven API base URL
_API_BASE = 'https://api.polyhaven.com'
_DL_BASE = 'https://dl.polyhaven.org/file/ph-assets'

# Pre-configured asset sets
ASSET_SETS = {
    'skin_studio': {
        'hdris': [
            {'name': 'studio_small_09', 'res': '2k', 'type': 'hdri'},
        ],
        'description': 'Studio HDRI for skin rendering',
    },
    'room_home': {
        'textures': [
            {'name': 'wood_floor', 'res': '2k', 'type': 'texture', 'surface': 'floor'},
            {'name': 'painted_plaster', 'res': '2k', 'type': 'texture', 'surface': 'wall'},
            {'name': 'white_plaster', 'res': '2k', 'type': 'texture', 'surface': 'ceiling'},
        ],
        'hdris': [
            {'name': 'modern_buildings_2', 'res': '2k', 'type': 'hdri'},
        ],
        'description': 'Home room: wood floor, painted walls, plaster ceiling',
    },
    'room_gym': {
        'textures': [
            {'name': 'rubber_tiles', 'res': '2k', 'type': 'texture', 'surface': 'floor'},
            {'name': 'concrete_wall', 'res': '2k', 'type': 'texture', 'surface': 'wall'},
            {'name': 'concrete_floor', 'res': '2k', 'type': 'texture', 'surface': 'ceiling'},
        ],
        'hdris': [
            {'name': 'industrial_workshop_foundry', 'res': '2k', 'type': 'hdri'},
        ],
        'description': 'Gym room: rubber floor, concrete walls, industrial HDRI',
    },
    'outdoor': {
        'hdris': [
            {'name': 'kloppenheim_06_puresky', 'res': '2k', 'type': 'hdri'},
        ],
        'description': 'Outdoor pure sky HDRI',
    },
}


def _ensure_cache_dir():
    """Create cache directory if needed."""
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _load_manifest():
    """Load download manifest (tracks what's cached)."""
    if os.path.exists(_MANIFEST_PATH):
        with open(_MANIFEST_PATH, 'r') as f:
            return json.load(f)
    return {}


def _save_manifest(manifest):
    """Save download manifest."""
    _ensure_cache_dir()
    with open(_MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=2)


def _download_file(url, dest_path, timeout=60):
    """Download a file from URL to local path."""
    _ensure_cache_dir()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    logger.info("Downloading %s → %s", url, os.path.basename(dest_path))
    req = Request(url, headers={'User-Agent': 'gtd3d/1.0 (muscle-tracker)'})

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        with open(dest_path, 'wb') as f:
            f.write(data)
        logger.info("Downloaded %.1f KB", len(data) / 1024)
        return dest_path
    except URLError as e:
        logger.error("Download failed: %s — %s", url, e)
        return None


def _asset_cache_path(asset_name, asset_type, res, ext):
    """Generate cache path for an asset."""
    return os.path.join(_CACHE_DIR, asset_type, f"{asset_name}_{res}{ext}")


def download_hdri(name, res='2k'):
    """
    Download an HDRI from PolyHaven.

    Args:
        name: PolyHaven HDRI name (e.g., 'studio_small_09')
        res: resolution ('1k', '2k', '4k')

    Returns:
        Local file path to .hdr file, or None on failure.
    """
    cache_path = _asset_cache_path(name, 'hdris', res, '.hdr')
    if os.path.exists(cache_path):
        logger.info("HDRI cached: %s", cache_path)
        return cache_path

    url = f"{_DL_BASE}/HDRIs/hdr/{res}/{name}_{res}.hdr"
    return _download_file(url, cache_path, timeout=120)


def download_texture(name, res='2k', maps=None):
    """
    Download PBR texture maps from PolyHaven.

    Args:
        name: PolyHaven texture name (e.g., 'wood_floor_deck')
        res: resolution ('1k', '2k', '4k')
        maps: list of map types to download. Default: ['diff', 'nor_gl', 'rough', 'ao']

    Returns:
        Dict mapping map_type → local file path. Missing maps are omitted.
    """
    if maps is None:
        maps = ['diff', 'nor_gl', 'rough', 'ao', 'disp']

    result = {}
    for map_type in maps:
        ext = '.jpg' if map_type == 'diff' else '.png'
        # PolyHaven uses .exr for some, .png for most — try png first
        cache_path = _asset_cache_path(f"{name}_{map_type}", 'textures', res, ext)
        if os.path.exists(cache_path):
            result[map_type] = cache_path
            continue

        # PolyHaven texture URL pattern
        url = f"{_DL_BASE}/Textures/{map_type}/{res}/{name}_{map_type}_{res}{ext}"
        path = _download_file(url, cache_path, timeout=90)
        if path:
            result[map_type] = path
        else:
            # Try .jpg fallback for non-diff maps
            if ext == '.png':
                cache_path_jpg = _asset_cache_path(f"{name}_{map_type}", 'textures', res, '.jpg')
                url_jpg = f"{_DL_BASE}/Textures/{map_type}/{res}/{name}_{map_type}_{res}.jpg"
                path = _download_file(url_jpg, cache_path_jpg, timeout=90)
                if path:
                    result[map_type] = path

    return result


def download_model(name, fmt='glb'):
    """
    Download a 3D model from PolyHaven.

    Args:
        name: PolyHaven model name
        fmt: format ('glb', 'fbx', 'blend')

    Returns:
        Local file path, or None on failure.
    """
    cache_path = _asset_cache_path(name, 'models', fmt, f'.{fmt}')
    if os.path.exists(cache_path):
        return cache_path

    url = f"{_DL_BASE}/Models/{fmt}/{name}.{fmt}"
    return _download_file(url, cache_path, timeout=180)


def get_asset_set(set_name, download=True):
    """
    Get all assets for a pre-configured set.

    Args:
        set_name: one of 'skin_studio', 'room_home', 'room_gym', 'outdoor'
        download: if True, download missing assets

    Returns:
        Dict with 'hdris' (list of paths), 'textures' (dict surface→{map→path}),
        'description' (str).
    """
    if set_name not in ASSET_SETS:
        logger.error("Unknown asset set: %s (available: %s)",
                     set_name, list(ASSET_SETS.keys()))
        return None

    asset_def = ASSET_SETS[set_name]
    result = {
        'hdris': [],
        'textures': {},
        'description': asset_def.get('description', ''),
    }

    # Download HDRIs
    for hdri in asset_def.get('hdris', []):
        if download:
            path = download_hdri(hdri['name'], hdri.get('res', '2k'))
        else:
            path = _asset_cache_path(hdri['name'], 'hdris', hdri.get('res', '2k'), '.hdr')
            if not os.path.exists(path):
                path = None
        if path:
            result['hdris'].append(path)

    # Download textures
    for tex in asset_def.get('textures', []):
        if download:
            maps = download_texture(tex['name'], tex.get('res', '2k'))
        else:
            maps = {}
            for mt in ['diff', 'nor_gl', 'rough', 'ao', 'disp']:
                for ext in ['.jpg', '.png']:
                    p = _asset_cache_path(f"{tex['name']}_{mt}", 'textures', tex.get('res', '2k'), ext)
                    if os.path.exists(p):
                        maps[mt] = p
                        break
        if maps:
            surface = tex.get('surface', tex['name'])
            result['textures'][surface] = maps

    return result


def list_cached():
    """List all cached assets."""
    if not os.path.exists(_CACHE_DIR):
        return {'hdris': [], 'textures': [], 'models': []}

    result = {}
    for category in ['hdris', 'textures', 'models']:
        cat_dir = os.path.join(_CACHE_DIR, category)
        if os.path.exists(cat_dir):
            result[category] = [f for f in os.listdir(cat_dir) if not f.startswith('.')]
        else:
            result[category] = []
    return result


def cache_size_mb():
    """Total cache size in MB."""
    total = 0
    for root, dirs, files in os.walk(_CACHE_DIR):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total / (1024 * 1024)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Available asset sets:", list(ASSET_SETS.keys()))
    cached = list_cached()
    print(f"Cached: {sum(len(v) for v in cached.values())} files, {cache_size_mb():.1f} MB")
