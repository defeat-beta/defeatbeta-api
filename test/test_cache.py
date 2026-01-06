import os
import shutil
import logging
from pathlib import Path
import duckdb
from defeatbeta_api.client.hugging_face_client import HuggingFaceClient
from defeatbeta_api.client.duckdb_client import DuckDBClient

# Configure logging to see our cache actions
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_cache")

def test_integration():
    print("Starting Integration Test...")
    
    # 1. Setup: Define a test cache directory to avoid messing with real data
    test_cache_name = "test_defeat_cache"
    
    # Clean up previous runs if they exist
    # For robust testing, we rely on the client to create it.
    
    # 2. Initialize Client
    print("\n[Step 1] Initializing HuggingFaceClient...")
    hf_client = HuggingFaceClient(cache_dir_name=test_cache_name)
    
    # 3. Trigger Download (Cache Miss)
    table_name = "stock_profile" # Small table example
    print(f"\n[Step 2] Resolving table '{table_name}' (should trigger download)...")
    
    local_path = hf_client.get_url_path(table_name)
    print(f" -> Local path resolved: {local_path}")
    
    # Verify file exists
    if not os.path.exists(local_path):
        print("FAIL: File was not created at expected path!")
        return
    print("PASS: File successfully cached on disk.")

    # 4. Initialize DuckDB Client (No httpfs)
    print("\n[Step 3] Initializing DuckDBClient...")
    db_client = DuckDBClient() # This will load your updated config
    
    # 5. Execute Query
    print("\n[Step 4] Querying data via DuckDB...")
    try:
        # We query the local path directly
        query = f"SELECT * FROM read_parquet('{local_path}') LIMIT 5"
        df = db_client.query(query)
        
        print("\nQuery Result Head:")
        print(df.head())
        
        if not df.empty:
             print("\nPASS: DuckDB successfully queried the local file.")
        else:
             print("\nWARN: DataFrame is empty (table might be empty, but query worked).")
             
    except Exception as e:
        print(f"\nFAIL: Query failed with error: {e}")
            
    # 6. Cleanup (Optional)
    # print("\n[Step 5] Cleaning up test cache...")
    # hf_client.cache.clear() 

if __name__ == "__main__":
    test_integration()
