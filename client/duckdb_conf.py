from utils.util import validate_memory_limit, validate_httpfs_cache_directory

http_timeout = 120000
memory_limit = '80%'
http_retries = 3
http_keep_alive = True
enable_http_metadata_cache = True
threads = 4
cache_httpfs_ignore_sigpipe = True
cache_httpfs_type = 'on_disk'
cache_httpfs_directory_name = 'defeat_cache'
cache_httpfs_disk_size = 1*1024*1024*1024
cache_httpfs_cache_block_size = 1*1024*1024
cache_httpfs_glob_cache_entry_size = 512
cache_httpfs_metadata_cache_entry_size = 512
cache_httpfs_file_handle_cache_entry_size = 512

duckdb_settings = [
    f"INSTALL cache_httpfs FROM community",
    f"LOAD cache_httpfs",
    f"SET GLOBAL http_timeout = {http_timeout}",
    f"SET GLOBAL memory_limit = '{validate_memory_limit(memory_limit)}'",
    f"SET GLOBAL http_retries = {http_retries}",
    f"SET GLOBAL http_keep_alive = {http_keep_alive}",
    f"SET GLOBAL enable_http_metadata_cache = {enable_http_metadata_cache}",
    f"SET GLOBAL threads = {threads}",
    f"SET GLOBAL cache_httpfs_ignore_sigpipe={cache_httpfs_ignore_sigpipe}",
    f"SET GLOBAL cache_httpfs_type='{cache_httpfs_type}'",
    f"SET GLOBAL cache_httpfs_cache_directory='{validate_httpfs_cache_directory(cache_httpfs_directory_name)}'",
    f"SET GLOBAL cache_httpfs_min_disk_bytes_for_cache={cache_httpfs_disk_size}",
    f"SET GLOBAL cache_httpfs_cache_block_size={cache_httpfs_cache_block_size}",
    f"SET GLOBAL cache_httpfs_profile_type='temp'",
    f"SET GLOBAL cache_httpfs_glob_cache_entry_size={cache_httpfs_glob_cache_entry_size}",
    f"SET GLOBAL cache_httpfs_metadata_cache_entry_size={cache_httpfs_metadata_cache_entry_size}",
    f"SET GLOBAL cache_httpfs_file_handle_cache_entry_size={cache_httpfs_file_handle_cache_entry_size}"
]