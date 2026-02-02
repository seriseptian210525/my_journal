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
        """
        Get the latest ingested timestamp for incremental loading.
        Ignores rows with empty customer_type to allow recovery from failed enrichment.
        """
        query = f"SELECT MAX(created_at) FROM {table_name} WHERE customer_type IS NOT NULL AND customer_type != ''"
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

    def upsert_df(self, df: pd.DataFrame, table_name: str = "unified_part_logs", 
                  conflict_cols: list = None, update_cols: list = None, chunksize: int = 1000):
        """
        Upsert DataFrame to table using ON CONFLICT DO UPDATE.
        
        Args:
            df: DataFrame to upsert
            table_name: Target table name
            conflict_cols: Columns for UNIQUE constraint (ON CONFLICT)
            update_cols: Columns to update on conflict (if None, updates all non-conflict cols)
            chunksize: Batch size for processing
        """
        if df.empty:
            print("   ⚠️ DataFrame is empty. Nothing to upsert.")
            return
        
        # Default conflict columns based on our schema
        if conflict_cols is None:
            conflict_cols = ['source_system', 'order_number', 'sku', 'item_name', 'year_cycle', 'pergantian_ke']
        
        # All columns from DataFrame
        all_cols = df.columns.tolist()
        
        # Update columns = all columns except conflict cols and 'id'
        if update_cols is None:
            update_cols = [c for c in all_cols if c not in conflict_cols and c != 'id']
        
        # Build column lists for SQL
        col_names = ', '.join(all_cols)
        placeholders = ', '.join([f':{c}' for c in all_cols])
        conflict_str = ', '.join(conflict_cols)
        update_str = ', '.join([f'{c} = EXCLUDED.{c}' for c in update_cols])
        
        # Add ingested_at update
        if 'ingested_at' not in update_cols:
            update_str += ', ingested_at = NOW()'
        
        upsert_query = f"""
        INSERT INTO {table_name} ({col_names})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_str})
        DO UPDATE SET {update_str}
        """
        
        total_rows = len(df)
        total_chunks = (total_rows // chunksize) + (1 if total_rows % chunksize else 0)
        print(f"   📤 Upserting {total_rows} rows in {total_chunks} chunks...")
        
        upserted = 0
        for i in range(0, total_rows, chunksize):
            chunk = df.iloc[i:i+chunksize]
            chunk_num = (i // chunksize) + 1
            
            try:
                with self.engine.begin() as conn:
                    for _, row in chunk.iterrows():
                        # Convert row to dict, handle NaN/NaT
                        params = {}
                        for col in all_cols:
                            val = row[col]
                            if pd.isna(val):
                                params[col] = None
                            else:
                                params[col] = val
                        conn.execute(text(upsert_query), params)
                
                upserted += len(chunk)
                print(f"      ✅ Chunk {chunk_num}/{total_chunks} ({len(chunk)} rows)")
            except Exception as e:
                print(f"      ❌ Chunk {chunk_num} failed: {str(e)[:150]}...")
                # Try smaller batch or individual rows
                self._upsert_rows_individually(chunk, upsert_query, all_cols, chunk_num)
        
        print(f"   📊 Total upserted: {upserted}/{total_rows} rows")
    
    def _upsert_rows_individually(self, chunk: pd.DataFrame, upsert_query: str, 
                                   all_cols: list, chunk_num: int):
        """Fallback: Upsert rows one by one."""
        success = 0
        failed = 0
        
        for _, row in chunk.iterrows():
            try:
                params = {}
                for col in all_cols:
                    val = row[col]
                    params[col] = None if pd.isna(val) else val
                
                with self.engine.begin() as conn:
                    conn.execute(text(upsert_query), params)
                success += 1
            except Exception as e:
                failed += 1
                if failed <= 3:
                    print(f"         📛 Row failed: {str(e)[:80]}...")
        
        if success > 0:
            print(f"      🔄 Chunk {chunk_num} recovered: {success}/{len(chunk)} rows via fallback")
        if failed > 0:
            print(f"      ⚠️ {failed} rows failed in chunk {chunk_num}")

    def truncate_table(self, table_name: str = "unified_part_logs"):
        """Truncate table (for full refresh)."""
        print(f"   🗑️ Truncating table {table_name}...")
        self.execute_query(f"TRUNCATE TABLE {table_name} RESTART IDENTITY;")
        print(f"   ✅ Table {table_name} truncated.")
    
    def get_row_count(self, table_name: str = "unified_part_logs") -> int:
        """Get current row count."""
        query = f"SELECT COUNT(*) FROM {table_name}"
        with self.engine.connect() as conn:
            result = conn.execute(text(query)).scalar()
        return result or 0
