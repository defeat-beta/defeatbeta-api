import hashlib
import json
import logging
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

class LocalHttpCache:
    """
    A persistent, file-based HTTP cache designed to replace cache_httpfs.
    
    Attributes:
        cache_dir (Path): The directory where cache files are stored.
        default_ttl (int): Default time-to-live in seconds (default: 86400 seconds which is 24 hours).
        debug (bool): If True, enables debug logging.
    """

    def __init__(self, cache_dir: Union[str, Path], default_ttl: int = 86400, debug: bool = False):
        self.cache_dir = Path(cache_dir).resolve()
        self.default_ttl = default_ttl
        self._ensure_cache_dir()
        self.DEBUG = debug
        if self.DEBUG:
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Initialized LocalHttpCache at {self.cache_dir} with default TTL {self.default_ttl} seconds.")

    def _ensure_cache_dir(self):
        """Creates the cache directory if it does not exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, url: str) -> str:
        """
        Generates a deterministic SHA-256 hash key for the given URL.
        """
        # Normalize URL to ensure consistency
        normalized_url = url.strip()
        return hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()

    def _get_paths(self, key: str) -> tuple[Path, Path]:
        """Returns the content path and metadata path for a key."""
        content_path = self.cache_dir / f"{key}.bin"
        meta_path = self.cache_dir / f"{key}.json"
        return content_path, meta_path

    def _is_valid(self, meta_path: Path) -> bool:
        """Checks if the cached entry is valid based on TTL."""
        if not meta_path.exists():
            return False
        
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            created_at = data.get("created_at", 0)
            ttl = data.get("ttl", 0)
            
            # 0 TTL implies infinite cache, otherwise check expiration
            if ttl > 0 and (time.time() - created_at) > ttl:
                return False
                
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def get_path(self, url: str, ttl: Optional[int] = None, force_refresh: bool = False) -> str:
        """
        Retrieves the local file path for a URL. Downloads it if not cached or expired.

        Args:
            url: The HTTP URL to retrieve.
            ttl: Custom TTL in seconds for this specific request. Defaults to class default.
            force_refresh: If True, ignores existing cache and re-downloads.

        Returns:
            str: The absolute path to the cached file (compatible with DuckDB).
        """
        key = self._generate_key(url)
        content_path, meta_path = self._get_paths(key)
        
        # Determine effective TTL
        effective_ttl = ttl if ttl is not None else self.default_ttl

        # Return existing cache if valid
        if not force_refresh and content_path.exists() and self._is_valid(meta_path):
            if self.DEBUG:
                logger.debug(f"Cache hit: {url} -> {content_path}")
            return str(content_path)

        if self.DEBUG:
            logger.info(f"Cache miss (downloading): {url}")
        
        # Download and cache
        try:
            self._download_file(url, content_path)
            self._write_metadata(url, meta_path, effective_ttl)
            return str(content_path)
        except Exception as e:
            logger.error(f"Failed to cache {url}: {e}")
            # If download fails but we have a stale version, we might optionally return it
            # For now, we propagate the error as the data is critical
            raise

    def _download_file(self, url: str, destination: Path):
        """Downloads file to a temp location then renames it for atomicity."""
        temp_path = destination.with_suffix(".tmp")
        
        # Use urllib for zero dependencies
        with urllib.request.urlopen(url) as response, temp_path.open("wb") as out_file:
            shutil.copyfileobj(response, out_file)
            
        # Atomic move to ensure readers don't see partial files
        temp_path.replace(destination)

    def _write_metadata(self, url: str, path: Path, ttl: int):
        """Writes metadata JSON file."""
        metadata = {
            "url": url,
            "created_at": time.time(),
            "ttl": ttl,
            "key": path.stem
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    def clear(self):
        """Clears the entire cache directory."""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self._ensure_cache_dir()
            if self.DEBUG:
                logger.info("Cache cleared.")

    def invalidate(self, url: str):
        """Removes a specific URL from the cache."""
        key = self._generate_key(url)
        content, meta = self._get_paths(key)
        if content.exists(): content.unlink()
        if meta.exists(): meta.unlink()
        if self.DEBUG:
            logger.debug(f"Invalidated: {url}")
