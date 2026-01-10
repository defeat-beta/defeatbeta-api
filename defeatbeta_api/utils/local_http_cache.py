import hashlib
import json
import logging
import os
import shutil
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Union, Dict

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

    def _get_server_headers(self, url: str) -> Dict[str, str]:
        """
        Performs a HEAD request. Handles redirects and extracts
        Hugging Face specific version headers if available.
        """
        try:
            req = urllib.request.Request(url, method="HEAD")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                headers = response.headers
                
                etag = headers.get("ETag")
                if self.DEBUG:
                    logger.debug(f"Server headers for {url}: ETag={etag}")
                
                return {
                    "etag": etag,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch headers for {url}: {e}")
            return {}

    def _is_cache_fresh(self, meta_path: Path, server_headers: Dict[str, str]) -> bool:
        """
        Determines if the cached file is fresh by comparing local metadata
        against current server headers.
        """
        if not meta_path.exists():
            if self.DEBUG: logger.debug("Cache miss: Metadata file not found.")
            return False
        
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                local_meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            if self.DEBUG: logger.debug("Cache miss: Metadata file corrupted.")
            return False
        
        # 1. Check Hugging Face Etag header first
        if server_headers.get("etag") and local_meta.get("etag"):
            server_etag_clean = server_headers["etag"].strip('"')
            local_etag_clean = local_meta["etag"].strip('"')
            
            if server_etag_clean == local_etag_clean:
                if self.DEBUG: logger.debug(f"Cache HIT (ETag match: {server_etag_clean})")
                return True
            else:
                if self.DEBUG: logger.debug(f"Cache STALE (ETag mismatch: Server={server_etag_clean} != Local={local_etag_clean})")
                return False
        
        # 2. Check TTL (Time To Live)
        # Used only if the server provided NO validation headers
        created_at = local_meta.get("created_at", 0)
        age = time.time() - created_at
        if age < self.default_ttl:
            if self.DEBUG: logger.debug(f"Cache HIT (TTL valid: {int(age)}s age < {self.default_ttl}s TTL). No server validation headers found.")
            return True

        if self.DEBUG: logger.info(f"Cache EXPIRED (TTL exceeded: {int(age)}s age > {self.default_ttl}s TTL)")
        return False


    def get_path(self, url: str, ttl: Optional[int] = None, force_refresh: bool = False) -> str:
        """
        Retrieves the local file path for a URL.
        Verifies freshness via HEAD request before returning cached content.
        """
        key = self._generate_key(url)
        content_path, meta_path = self._get_paths(key)
        
        # 1. If force_refresh is True, skip all checks and download
        if not force_refresh and content_path.exists():
            # Check with server if our file is still good
            server_headers = self._get_server_headers(url)
            
            if self._is_cache_fresh(meta_path, server_headers):
                return str(content_path)

        # 2. Download (Cache Miss or Stale)
        if self.DEBUG: logger.info(f"Downloading (Cache miss/stale): {url}")
        try:
            self._download_and_save(url, content_path, meta_path)
            return str(content_path)
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            raise


    def _download_and_save(self, url: str, content_path: Path, meta_path: Path):
        """Downloads the file and saves metadata atomically."""
        temp_content = content_path.with_suffix(".tmp")
        
        try:
            # Use urllib for zero dependencies
            with urllib.request.urlopen(url, timeout=60) as response, temp_content.open("wb") as out_file:
                shutil.copyfileobj(response, out_file)
                
                # Extract headers for next time
                metadata = {
                    "url": url,
                    "created_at": time.time(),
                    "etag": response.headers.get("ETag"),
                    "key": content_path.stem
                }

            # Atomic Move
            temp_content.replace(content_path)
            
            # Write Metadata
            with meta_path.open("w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
                
        except Exception:
            # Cleanup temp file on failure
            if self.DEBUG: logger.error(f"Failed to download or save cache for {url}")
            if temp_content.exists():
                temp_content.unlink()
            raise


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
