import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from src.common.config import NEON_DB_CONNECTION_STRING

class NeonLoader:
    """
    Handles connection and operations for Neon PostgreSQL.
    """
    def __init__(self):
        if not NEON_DB_CONNECTION_STRING:
            raise ValueError("❌ NEON_DB_CONNECTION_STRING is missing in .env or config!")
        # Use connection pooling
        self.engine = create_engine(NEON_DB_CONNECTION_STRING, pool_pre_ping=True)

    def execute_query(self, query: str, params: dict = None):
        """Executes a SQL query (DDL/DML)."""
        with self.engine.begin() as conn:  # .begin() manages transactions/commit automatically
            result = conn.execute(text(query), params or {})
            return result

    def get_max_created_at(self, table_name: str = "unified_part_logs"):
        """Get the latest ingested timestamp for incremental loading."""
        query = f"SELECT MAX(created_at) FROM {table_name}"
        with self.engine.connect() as conn:
            result = conn.execute(text(query)).scalar()
        return result

    def fetch_df(self, query: str, params: dict = None):
        """Fetch query results as DataFrame."""
        with self.engine.connect() as conn:
            return pd.read_sql(text(query), conn, params=params)
            
    def load_df_append(self, df: pd.DataFrame, table_name: str, chunksize: int = 5000):
        """
        Appends DataFrame to table using chunked inserts for reliability.
        Handles large datasets by breaking into smaller batches.
        """
        if df.empty:
            print("   ⚠️ DataFrame is empty. Nothing to insert.")
            return
        
        total_rows = len(df)
        total_chunks = (total_rows // chunksize) + (1 if total_rows % chunksize else 0)
        
        print(f"   📤 Uploading {total_rows} rows in {total_chunks} chunks...")
        
        # Process chunks
        inserted = 0
        for i in range(0, total_rows, chunksize):
            chunk = df.iloc[i:i+chunksize]
            chunk_num = (i // chunksize) + 1
            
            try:
                chunk.to_sql(
                    table_name, 
                    self.engine, 
                    if_exists='append', 
                    index=False,
                    method='multi'  # Use multi-row insert for efficiency
                )
                inserted += len(chunk)
                print(f"      ✅ Chunk {chunk_num}/{total_chunks} ({len(chunk)} rows)")
            except Exception as e:
                # Log the error but continue with remaining chunks
                print(f"      ❌ Chunk {chunk_num} failed: {str(e)[:100]}...")
                # Try single-row insert for debugging
                self._insert_rows_individually(chunk, table_name, chunk_num)
        
        print(f"   📊 Total inserted: {inserted}/{total_rows} rows")
    
    def _insert_rows_individually(self, chunk: pd.DataFrame, table_name: str, chunk_num: int):
        """
        Fallback: Insert rows one by one to isolate problematic records.
        """
        success = 0
        failed_rows = []
        
        for idx, row in chunk.iterrows():
            try:
                row_df = pd.DataFrame([row])
                row_df.to_sql(table_name, self.engine, if_exists='append', index=False)
                success += 1
            except Exception as e:
                failed_rows.append({
                    'index': idx,
                    'error': str(e)[:50],
                    'sample': str(row.to_dict())[:100]
                })
                if len(failed_rows) <= 3:  # Only log first 3 failures
                    print(f"         📛 Row {idx} failed: {str(e)[:80]}...")
        
        if success > 0:
            print(f"      🔄 Chunk {chunk_num} recovered: {success}/{len(chunk)} rows via fallback")
        if failed_rows:
            print(f"      ⚠️ {len(failed_rows)} rows could not be inserted")
