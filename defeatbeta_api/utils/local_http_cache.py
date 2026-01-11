import hashlib
import json
import logging
import shutil
import time
import threading
import urllib.request
from pathlib import Path
from typing import Optional, Union, Dict, List
from urllib3.util.retry import Retry
import requests
from requests.adapters import HTTPAdapter
import pickle
import pyarrow as pa
import pyarrow.parquet as pq
from defeatbeta_api.utils.util import columns_from_decimal_to_float

logger = logging.getLogger(__name__)


class HTTPRangeReader:
    """
    Helper class for reading specific byte ranges from remote URLs using HTTP range requests.
    Uses requests.Session for connection pooling to improve performance on Windows.
    """
    def __init__(self, url: str, debug: bool = False):
        self.url = url
        self.debug = debug
        self._size = None
        self._supports_ranges = None
        
        # Initialize session with optimized settings for Windows performance
        self.session = requests.Session()
        retry_strategy = Retry(
            total=2,  # Retries
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET"]
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy, 
            pool_connections=5,  # Allow 5 concurrent connections 
            pool_maxsize=5  # Maintain 5 connections in pool
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        # Set optimized headers for range requests
        self.session.headers.update({
            'User-Agent': 'DefeatBeta-LocalCache/1.0',
            'Connection': 'keep-alive',
            'Accept-Encoding': 'gzip, deflate'
        })

    def _get_file_size(self) -> int:
        """Fetch file size from Content-Length header, following redirects if needed."""
        if self._size is not None:
            return self._size
        try:
            # First try HEAD with redirects followed
            response = self.session.head(self.url, timeout=10, allow_redirects=True)
            
            # Check for X-Linked-Size (HuggingFace specific header for actual file size)
            if 'X-Linked-Size' in response.headers:
                size_str = response.headers.get('X-Linked-Size')
                self._size = int(size_str)
                return self._size
            
            # Fall back to Content-Length
            content_length = response.headers.get("Content-Length")
            if content_length:
                self._size = int(content_length)
                return self._size
            else:
                # Fallback to GET if HEAD fails to provide length (rare)
                raise RuntimeError(f"Server did not provide Content-Length or X-Linked-Size for {self.url}")
        except Exception as e:
            logger.error(f"Failed to get file size for {self.url}: {e}")
            raise

    def supports_range_requests(self) -> bool:
        """
        Check if server supports HTTP range requests.

        (Gets HEAD and checks 'Accept-Ranges' header)
        """
        if self._supports_ranges is not None:
            return self._supports_ranges
        try:
            response = self.session.head(self.url, timeout=10)
            accept_ranges = response.headers.get("Accept-Ranges", "").lower()
            self._supports_ranges = accept_ranges == "bytes"
            if self.debug:
                logger.debug(f"Server supports range requests: {self._supports_ranges}")
            return self._supports_ranges
        except Exception as e:
            logger.warning(f"Failed to check range request support for {self.url}: {e}")
            self._supports_ranges = False
            return False

    def read_range(self, start: int, end: int) -> bytes:
        """
        Read a specific byte range from the remote file.
        Args:
            start: Starting byte position (inclusive)
            end: Ending byte position (inclusive)
        """
        try:
            # HTTP range header is "start-end" (inclusive on both ends)
            headers = {"Range": f"bytes={start}-{end}"}
            response = self.session.get(self.url, headers=headers, timeout=60)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to read range {start}-{end} from {self.url}: {e}")
            raise

    def read_all(self) -> bytes:
        """Read the entire file content."""
        try:
            response = self.session.get(self.url, timeout=60)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to read entire file from {self.url}: {e}")
            raise

    def __len__(self) -> int:
        return self._get_file_size()

    def close(self):
        """Close the session."""
        self.session.close()
    
    def __del__(self):
        try:
            self.close()
        except:
            pass

class RangeRequestFile:
    """
    File-like object that reads from a remote URL using HTTP range requests.
    Compatible with PyArrow's ParquetFile interface.
    Includes read-ahead buffering to minimize HTTP requests.
    """
    def __init__(self, url: str, reader: HTTPRangeReader, debug: bool = False, buffer_size: int = 8 * 1024 * 1024):
        self.url = url
        self.reader = reader
        self.debug = debug
        self.position = 0
        self._size = len(reader)
        self.closed = False
        
        # Larger buffering for better performance on Windows (8MB default)
        self.buffer_size = buffer_size
        self._buffer = b""
        self._buffer_start = -1
        self._buffer_end = -1

    def _fill_buffer(self, start: int, size: int):
        """Fetch a chunk of data into the buffer."""
        # Align read to buffer_size boundaries or just read what's requested + lookahead
        read_start = start
        read_end = min(start + max(size, self.buffer_size), self._size)
        
        if self.debug:
            print(f"[DEBUG] Buffering: Fetching {read_start}-{read_end} ({read_end - read_start} bytes)")
            
        self._buffer = self.reader.read_range(read_start, read_end - 1)
        self._buffer_start = read_start
        self._buffer_end = read_end

    def read(self, n: int = -1) -> bytes:
        """Read n bytes from current position."""
        if n == -1 or n is None:
            n = self._size - self.position
        
        if n <= 0:
            return b""
        
        target_end = min(self.position + n, self._size)
        real_n = target_end - self.position
        
        # Check if request is fully within current buffer
        if (self.position >= self._buffer_start and 
            target_end <= self._buffer_end):
            offset = self.position - self._buffer_start
            data = self._buffer[offset:offset + real_n]
            self.position += len(data)
            return data
            
        # Buffer miss: fetch new data
        self._fill_buffer(self.position, real_n)
        
        # Return from new buffer
        offset = self.position - self._buffer_start
        data = self._buffer[offset:offset + real_n]
        self.position += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0: # SEEK_SET
            self.position = offset
        elif whence == 1: # SEEK_CUR
            self.position += offset
        elif whence == 2: # SEEK_END
            self.position = self._size + offset
        
        self.position = max(0, min(self.position, self._size))
        return self.position

    def tell(self) -> int:
        return self.position

    def __len__(self) -> int:
        return self._size

    def readable(self) -> bool: return not self.closed
    def seekable(self) -> bool: return True
    def close(self): self.closed = True
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()

logger = logging.getLogger(__name__)


class LocalHttpCache:
    """
    A persistent, file-based HTTP cache designed to replace cache_httpfs.
    
    Attributes:
        cache_dir (Path): The directory where cache files are stored.
        debug (bool): If True, enables debug logging.
    """

    def __init__(self, cache_dir: Union[str, Path], debug: bool = False):
        self.cache_dir = Path(cache_dir).resolve()
        self._ensure_cache_dir()
        self.DEBUG = debug
        
        # In-memory cache for recently accessed items to avoid repeated disk I/O
        self._memory_cache: Dict[str, any] = {}  # key -> data
        self._memory_cache_lock = threading.RLock()
        self.max_memory_cache_size = 10  # Max 10 items in memory cache
        
        # Track last HEAD request times to avoid excessive server checks
        self._last_head_check: Dict[str, float] = {}  # url -> timestamp
        self._head_check_interval = 1  # Only check server every 1 second for same URL
        
        if self.DEBUG:
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Initialized LocalHttpCache at {self.cache_dir}.")

    def _ensure_cache_dir(self):
        """Creates the cache directory if it does not exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _convert_url_to_hash(self, url: str) -> str:
        """
        Generates a deterministic SHA-256 hash key for the given URL.
        """
        normalized_url = url.strip()
        return hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()

    def _get_preload_cache_files_paths(self, key: str) -> tuple[Path, Path]:
        """Returns the content path and metadata path for a key (preload mode)."""
        content_path = self.cache_dir / f"{key}.bin" # Contains data
        meta_path = self.cache_dir / f"{key}.json" # Contains ETag which is used to compare with hugging face's data freshness
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
        
        # Load local metadata
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                local_meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            if self.DEBUG: logger.debug("Cache miss: Metadata file corrupted.")
            return False
        
        # Check Hugging Face ETag header for freshness
        if server_headers.get("etag") and local_meta.get("etag"):
            server_etag = server_headers["etag"].strip('"')
            local_etag = local_meta["etag"].strip('"')
            
            if server_etag == local_etag:
                if self.DEBUG: logger.debug(f"Cache up-to-date (ETag match: {server_etag})")
                return True
            else:
                if self.DEBUG: logger.debug(f"Cache out-dated (ETag mismatch: Server={server_etag} != Local={local_etag})")
                return False
        
        # If no ETag available, consider cache stale to ensure fresh data
        if self.DEBUG: logger.debug("Cache out-dated (no ETag available for validation)")
        return False


    def get_path(self, url: str, force_refresh: bool = False) -> str:
        """
        Retrieves the local file path for a URL.
        Optimized to reduce unnecessary HEAD requests and use in-memory caching.
        """
        key = self._convert_url_to_hash(url)
        content_path, meta_path = self._get_preload_cache_files_paths(key)
        
        # 1. If force_refresh is True, skip all checks and download
        if force_refresh:
            if self.DEBUG: logger.info(f"Force refresh: downloading {url}")
            self._download_and_save(url, content_path, meta_path)
            return str(content_path)
        
        # 2. Check if file exists in cache
        if not content_path.exists():
            if self.DEBUG: logger.info(f"Not cached: downloading {url}")
            self._download_and_save(url, content_path, meta_path)
            return str(content_path)
        
        # 3. If we checked the server very recently, skip ETag check and use cache
        if meta_path.exists():
            try:
                # If we checked the server recently, don't check again
                last_check = self._last_head_check.get(url, 0)
                if time.time() - last_check < self._head_check_interval:
                    if self.DEBUG: logger.debug(f"Cache up-to-date (server recently checked): {url}")
                    return str(content_path)
                
            except Exception:
                pass  # Fallback to server check
        
        # 4. Check with server if our file is still up-to-date
        server_headers = self._get_server_headers(url)
        self._last_head_check[url] = time.time()
        
        if self._is_cache_fresh(meta_path, server_headers):
            return str(content_path)

        # 5. Download (Cache out-dated)
        if self.DEBUG: logger.info(f"Cache out-dated: downloading {url}")
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
            with requests.get(url, stream=True, timeout=60) as response:
                response.raise_for_status() # Raise error for bad responses

                with temp_content.open("wb") as out_file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024): # 1MB chunks for memory efficiency
                        if chunk:
                            out_file.write(chunk)

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
            if self.DEBUG:
                logger.error(f"Failed to download or save cache for {url}")

            if temp_content.exists():
                try:
                    temp_content.unlink() # Remove temp corrupted file
                except Exception:
                    pass
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
        key = self._convert_url_to_hash(url)
        content, meta = self._get_preload_cache_files_paths(key)
        if content.exists(): content.unlink()
        if meta.exists(): meta.unlink()
        if self.DEBUG:
            logger.debug(f"Invalidated: {url}")

    # ============================================================================
    # Parquet-specific methods for HTTP range requests (cache_httpfs alternative)
    # ============================================================================

    def _cache_row_group_data(self, cache_key: str, table: 'pa.Table') -> None:
        """
        Cache a row group as Arrow IPC format with in-memory caching.
        
        (Using Arrow IPC format for faster read/write compared to Parquet)
        """
        try:
            # Store in memory cache immediately for fast access
            self._store_in_memory_cache(cache_key, table)
            
            # Also store to disk for persistence
            cache_path = self._get_cached_path(cache_key, create=True, extension='.arrow')
            
            # Write table using Arrow IPC format
            with open(str(cache_path), 'wb') as f:
                writer = pa.ipc.new_stream(f, table.schema)
                writer.write_table(table)
                writer.close()
            
            if self.DEBUG:
                logger.debug(f"Cached row group data to disk and memory: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache row group data: {e}")

    def _load_cached_row_group(self, cache_key: str) -> Optional['pa.Table']:
        """
        Load a cached row group from Arrow IPC format with in-memory caching.

        First checks in-memory cache, then disk cache.
        """
        try:
            # 1. Check in-memory cache
            memory_data = self._get_from_memory_cache(cache_key)
            if memory_data is not None:
                if self.DEBUG: logger.debug(f"Memory cache found: {cache_key}")
                return memory_data
                
            # 2. Check disk cache
            cache_path = self._get_cached_path(cache_key, extension='.arrow')
            if cache_path and cache_path.exists():
                with open(str(cache_path), 'rb') as f:
                    reader = pa.ipc.open_stream(f)
                    table = reader.read_all()
                    
                # Store in memory cache for next time
                self._store_in_memory_cache(cache_key, table)
                if self.DEBUG: logger.debug(f"Disk cache found (stored in memory): {cache_key}")
                return table
        except Exception as e:
            logger.warning(f"Failed to load cached row group: {e}")
        return None

    def _get_cached_path(self, cache_key: str, create: bool = False, extension: str = '.parquet') -> Optional[Path]:
        """Get the cache file path for a cache key (sha256 hashed)."""
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()
        cache_file = self.cache_dir / f"{key_hash}{extension}"
        if create:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
        return cache_file
    
    def _get_from_memory_cache(self, key: str):
        """Get data from in-memory cache (always fresh since ETag validated on every access)."""
        with self._memory_cache_lock:
            if key in self._memory_cache:
                if self.DEBUG:
                    logger.debug(f"Memory cache found: {key}")
                return self._memory_cache[key]
        return None
    
    def _store_in_memory_cache(self, key: str, data):
        """
        Store data in in-memory cache.

        If memory cache exceeds max size, evict oldest entry.

        Example flow: Memory cache full -> Evict oldest -> from disk cache or if not found, new download -> add to memory cache
        """
        with self._memory_cache_lock:
            # Limit memory cache size to prevent memory bloat
            if len(self._memory_cache) > self.max_memory_cache_size:
                # Remove oldest entries (arbitrary removal since no timestamps)
                oldest_key = next(iter(self._memory_cache))
                if self.DEBUG:
                    logger.debug(f"Memory cache full, evicting oldest entry: {oldest_key}")
                del self._memory_cache[oldest_key]
            self._memory_cache[key] = data
    

    def _find_matching_row_groups_live(self, pf, column, value) -> List[int]:
        """
        Find matching row groups using an open ParquetFile object (live network/file).
        """
        matching = []
        
        # 1. Find the index of the filter column
        col_idx = -1
        if pf.schema_arrow and pf.schema_arrow.names:
            try:
                col_idx = pf.schema_arrow.names.index(column)
            except ValueError:
                pass # Column not found
        
        if col_idx == -1:
            if self.DEBUG: logger.debug(f"Column {column} not found in schema, reading all row groups.")
            return list(range(pf.num_row_groups))

        # 2. Check statistics for each row group
        for i in range(pf.num_row_groups):
            rg = pf.metadata.row_group(i)
            col = rg.column(col_idx)
            
            # If statistics are available, use them to filter
            if col.is_stats_set and col.statistics:
                try:
                    # Check if value is within min/max range
                    if col.statistics.min <= value <= col.statistics.max:
                        matching.append(i)
                except Exception:
                    # If comparison fails (e.g. type mismatch), assume match to be safe
                    matching.append(i)
            else:
                # No statistics available, must read this row group
                matching.append(i)
        return matching

    def _find_matching_row_groups_from_meta(self, meta, column, value) -> List[int]:
        """
        Find matching row groups using cached metadata dictionary (no network).
        """
        matching = []
        for i, rg_stats in enumerate(meta['row_groups']):
            if column in rg_stats:
                stats = rg_stats[column]
                # Check min/max range safely
                try:
                    if stats['min'] <= value <= stats['max']:
                        matching.append(i)
                except Exception:
                    # If comparison fails, assume match
                    matching.append(i)
            else:
                # Column stats not in cache or column missing, must read
                matching.append(i)
        return matching

    def read_parquet_metadata(self, url: str) -> Dict:
        """
        Read only the Parquet metadata (footer) without fetching the full file.
        """
        try:
            # Try HTTP range requests first (only fetches footer)
            if self._url_supports_range_requests(url):
                if self.DEBUG:
                    logger.debug(f"Fetching Parquet metadata for {url} via range requests")
                
                reader = HTTPRangeReader(url, debug=self.DEBUG)
                range_file = RangeRequestFile(url, reader, debug=self.DEBUG)
                
                try:
                    parquet_file = pq.ParquetFile(range_file)
                    
                    metadata = {
                        'schema': str(parquet_file.schema_arrow),
                        'num_rows': parquet_file.metadata.num_rows,
                        'num_row_groups': parquet_file.metadata.num_row_groups,
                        'column_names': parquet_file.schema_arrow.names,
                        'metadata': parquet_file.metadata,
                    }
                    
                    if self.DEBUG:
                        logger.debug(f"Metadata fetched via range requests: {parquet_file.metadata.num_rows} rows")
                    return metadata
                    
                finally:
                    reader.close() # Ensure connection is closed

            # Fallback: Download entire file to cache
            local_path = self.get_path(url)
            parquet_file = pq.ParquetFile(local_path)
            
            metadata = {
                'schema': str(parquet_file.schema_arrow),
                'num_rows': parquet_file.metadata.num_rows,
                'num_row_groups': parquet_file.metadata.num_row_groups,
                'column_names': parquet_file.schema_arrow.names,
                'metadata': parquet_file.metadata,
            }
            
            if self.DEBUG:
                logger.debug(f"Metadata fetched from cache: {parquet_file.metadata.num_rows} rows")
            return metadata

        except Exception as e:
            logger.error(f"Failed to read metadata from {url}: {e}")
            raise

    def read_parquet_by_filter(
        self,
        url: str,
        filter_column: str,
        filter_value: str,
        columns: Optional[List[str]] = None,
        row_group_indices: Optional[List[int]] = None
    ):
        """Optimized filtered reading with improved caching."""
        # Simple cache key for the entire filtered result
        filter_cache_key = f"{url}#filtered#{filter_column}={filter_value}"
        
        # Check if the entire filtered result is already cached in memory
        if row_group_indices is None:  # Only use full result cache when not specifying row groups
            cached_result = self._get_from_memory_cache(filter_cache_key)
            if cached_result is not None:
                if self.DEBUG: logger.debug(f"Filtered result cache found in memory: {filter_cache_key}")
                if columns:
                    return cached_result.select(columns)
                return cached_result
        
        # Metadata Caching
        meta_cache_key = f"{url}#metadata_stats_v1"
        meta_cache_path = self._get_cached_path(meta_cache_key, extension='.pickle')
        
        pf = None
        reader = None
        
        # 1. Resolve Row Groups (Try Cache -> Then Network)
        if row_group_indices is None:
            # Try loading metadata from disk
            if meta_cache_path.exists():
                try:
                    with open(meta_cache_path, 'rb') as f:
                        file_meta = pickle.load(f)
                    
                    if self.DEBUG: logger.debug("Using cached metadata for row group resolution")
                    row_group_indices = self._find_matching_row_groups_from_meta(
                        file_meta, filter_column, filter_value
                    )
                except Exception as e:
                    logger.warning(f"Failed to load cached metadata: {e}")
            
            # If still unknown, fetch metadata from server
            if row_group_indices is None:
                if self.DEBUG: logger.debug("Fetching Parquet metadata from server")
                reader = HTTPRangeReader(url, debug=self.DEBUG)
                range_file = RangeRequestFile(url, reader, debug=self.DEBUG)
                pf = pq.ParquetFile(range_file)
                
                # Cache the metadata for next time
                try:
                    meta_store = {
                        'num_row_groups': pf.num_row_groups,
                        'row_groups': []
                    }
                    # Extract only needed stats to keep pickle small
                    for i in range(pf.num_row_groups):
                        rg = pf.metadata.row_group(i)
                        rg_stats = {}
                        for j in range(rg.num_columns):
                            col = rg.column(j)
                            name = col.path_in_schema
                            if col.statistics:
                                rg_stats[name] = {
                                    'min': col.statistics.min, 
                                    'max': col.statistics.max
                                }
                        meta_store['row_groups'].append(rg_stats)
                        
                    with open(meta_cache_path, 'wb') as f:
                        pickle.dump(meta_store, f)
                        
                    if self.DEBUG: logger.debug(f"Cached metadata for {pf.num_row_groups} row groups")
                except Exception as e:
                    logger.warning(f"Failed to cache metadata: {e}")

                row_group_indices = self._find_matching_row_groups_live(pf, filter_column, filter_value)

        # 2. Read Data with improved caching
        tables = []
        for rg_idx in row_group_indices:
            cache_key = f"{url}#row_group={rg_idx}"
            
            # Check cache (memory first, then disk)
            cached_table = self._load_cached_row_group(cache_key)
            if cached_table is not None:
                if self.DEBUG: logger.debug(f"Cache found for row group {rg_idx}")
                tables.append(cached_table)
                continue

            # Need to download this row group
            if pf is None:
                if reader is None:
                    reader = HTTPRangeReader(url, debug=self.DEBUG)
                range_file = RangeRequestFile(url, reader, debug=self.DEBUG)
                pf = pq.ParquetFile(range_file)
            
            rg_table = pf.read_row_group(rg_idx, columns=columns)
            self._cache_row_group_data(cache_key, rg_table)
            tables.append(rg_table)

        if reader:
            reader.close()
            
        if not tables:
            # Handle empty result case
            if pf is None:
                reader = HTTPRangeReader(url, debug=self.DEBUG)
                range_file = RangeRequestFile(url, reader, debug=self.DEBUG)
                pf = pq.ParquetFile(range_file)
            result = pf.read_row_group(0, columns=columns).slice(0, 0)
            if reader:
                reader.close()
            return result

        # Combine and filter results
        combined = pa.concat_tables(tables)
        filtered = combined.filter(pa.compute.equal(combined[filter_column], filter_value))
        
        # Cache the full filtered result in memory for quick re-access
        if row_group_indices is None:  # Only cache when we did full discovery
            self._store_in_memory_cache(filter_cache_key, filtered)
        return filtered

    def _url_supports_range_requests(self, url: str) -> bool:
        """
        Check if a URL supports HTTP range requests.

        (Caches the result to avoid repeated HEAD requests)
        """
        try:
            reader = HTTPRangeReader(url, debug=self.DEBUG)
            supports = reader.supports_range_requests()
            
            if self.DEBUG:
                logger.debug(f"URL {url} supports range requests: {supports}")
            return supports
        except Exception as e:
            logger.warning(f"Could not determine if {url} supports range requests: {e}")
            return False

    def cache_query_result(self, cache_key: str, dataframe) -> None:
        """
        Cache a pandas DataFrame query result for instant retrieval.
        
        (Converts Decimal columns to float before caching to avoid type issues
        when the cached data is later used in arithmetic operations)
        """
        try:
            # Convert Decimal columns to float before caching
            # This ensures cached data is immediately usable in calculations (for example TTM columns)
            df_to_cache = columns_from_decimal_to_float(dataframe)
            
            # Store in memory cache for immediate access
            self._store_in_memory_cache(cache_key, df_to_cache)
            
            # Also store to disk as pickle for persistence
            cache_path = self._get_cached_path(cache_key, create=True, extension='.pkl')
            
            with open(cache_path, 'wb') as f:
                pickle.dump(df_to_cache, f, protocol=pickle.HIGHEST_PROTOCOL)
                
            if self.DEBUG:
                logger.debug(f"Cached query result: {len(df_to_cache)} rows to {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache query result: {e}")
    
    def get_cached_query_result(self, cache_key: str, url: str = None):
        """Retrieve a cached pandas DataFrame query result if fresh.
        
        Always validates the parquet file ETag to detect upstream updates.
        Only returns cached data if ETag hasn't changed.
        
        Args:
            cache_key: The cache key for this query result
            url: Optional parquet file URL to validate ETag against
        
        Returns:
            Cached result if parquet file unchanged, None otherwise
        """
        try:
            # Check memory cache first (fastest)
            memory_result = self._get_from_memory_cache(cache_key)
            if memory_result is not None:
                # If URL provided, validate parquet file hasn't changed
                if url:
                    server_headers = self._get_server_headers(url)
                    key = self._convert_url_to_hash(url)
                    _, meta_path = self._get_preload_cache_files_paths(key)
                    
                    # Only check freshness if we have a cached metadata file to compare
                    if meta_path.exists():
                        if not self._is_cache_fresh(meta_path, server_headers):
                            if self.DEBUG:
                                logger.debug(f"Parquet file has been updated, invalidating query result cache: {cache_key}")
                            return None  # Force re-fetch from server
                
                if self.DEBUG:
                    logger.debug(f"Query result memory cache found: {cache_key}")
                return memory_result
            
            # Check disk cache
            cache_path = self._get_cached_path(cache_key, extension='.pkl')
            if cache_path and cache_path.exists():
                with open(cache_path, 'rb') as f:
                    result = pickle.load(f)
                
                # If URL provided, validate parquet file hasn't changed
                if url:
                    server_headers = self._get_server_headers(url)
                    key = self._convert_url_to_hash(url)
                    _, meta_path = self._get_preload_cache_files_paths(key)
                    
                    # Only check freshness if we have a cached metadata file to compare
                    if meta_path.exists():
                        if not self._is_cache_fresh(meta_path, server_headers):
                            if self.DEBUG:
                                logger.debug(f"Parquet file has been updated, invalidating query result cache: {cache_key}")
                            return None  # Force re-fetch from server
                
                # Store back in memory for next time
                self._store_in_memory_cache(cache_key, result)
                
                if self.DEBUG:
                    logger.debug(f"Query result disk cache found: {cache_key} ({len(result)} rows)")
                return result
            
        except Exception as e:
            logger.warning(f"Failed to retrieve cached query result: {e}")
        return None

