#!/usr/bin/env python3
# scripts/collect_data.py - GitHub Actions Data Collection Script
# --------------------------------------------------

import json
import os
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configuration
API_URL = "https://djfunds-static.imedao.com/djapi/index_eva/dj"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"
}
DATA_FILE = "data/valuation_history.json"

def fetch_api_data() -> Tuple[List[Dict], Optional[str]]:
    """Fetch current data from API."""
    try:
        print(f"[INFO] Fetching data from API: {API_URL}")
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        if 'data' not in data or 'items' not in data['data']:
            return [], "Invalid API response structure"
        
        items = data['data']['items']
        print(f"[SUCCESS] Fetched {len(items)} items from API")
        return items, None
        
    except Exception as e:
        error_msg = f"Error fetching data from API: {e}"
        print(f"[ERROR] {error_msg}")
        return [], error_msg

def load_existing_data() -> List[Dict]:
    """Load existing historical data from JSON file."""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[INFO] Loaded {len(data)} existing records")
                return data
        else:
            print("[INFO] No existing data file found, starting fresh")
            return []
    except Exception as e:
        print(f"[WARNING] Error loading existing data: {e}")
        return []

def data_exists_for_date(data: List[Dict], date: str) -> bool:
    """Check if data already exists for a specific date."""
    return any(item.get('fetch_date') == date for item in data)

def prepare_records(items: List[Dict], fetch_date: str) -> List[Dict]:
    """Prepare API items for storage with metadata."""
    fetch_timestamp = int(datetime.now().timestamp())
    records = []
    
    for item in items:
        record = item.copy()
        record['fetch_date'] = fetch_date
        record['fetch_timestamp'] = fetch_timestamp
        
        # Fix API typos
        if 'yeild' in record:
            record['dividend_yield'] = record.pop('yeild')
        if 'bond_yeild' in record:
            record['bond_yield'] = record.pop('bond_yeild')
        
        records.append(record)
    
    return records

def save_data(data: List[Dict]) -> bool:
    """Save data to JSON file."""
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        
        # Sort data by date (newest first) and name
        data.sort(key=lambda x: (x.get('fetch_date', ''), x.get('name', '')), reverse=True)
        
        # Save to JSON with pretty formatting
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[SUCCESS] Saved {len(data)} records to {DATA_FILE}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error saving data: {e}")
        return False

def cleanup_old_data(data: List[Dict], days_to_keep: int = 90) -> List[Dict]:
    """Remove data older than specified days."""
    from datetime import timedelta
    
    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
    original_count = len(data)
    
    filtered_data = [item for item in data if item.get('fetch_date', '') >= cutoff_date]
    
    removed_count = original_count - len(filtered_data)
    if removed_count > 0:
        print(f"[CLEANUP] Cleaned up {removed_count} old records (keeping last {days_to_keep} days)")
    
    return filtered_data

def get_data_summary(data: List[Dict]) -> Dict:
    """Get summary statistics about the data."""
    if not data:
        return {'total_records': 0}
    
    dates = set(item.get('fetch_date') for item in data)
    indices = set(item.get('index_code') for item in data)
    
    return {
        'total_records': len(data),
        'total_days': len(dates),
        'total_indices': len(indices),
        'earliest_date': min(dates) if dates else None,
        'latest_date': max(dates) if dates else None,
        'file_size_mb': round(os.path.getsize(DATA_FILE) / 1024 / 1024, 2) if os.path.exists(DATA_FILE) else 0
    }

def main():
    """Main data collection function."""
    print("[START] Starting daily valuation data collection...")
    
    # Get environment variables
    force_update = os.getenv('FORCE_UPDATE', 'false').lower() == 'true'
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"[INFO] Collection date: {today}")
    print(f"[INFO] Force update: {force_update}")
    
    # Load existing data
    existing_data = load_existing_data()
    
    # Check if data already exists for today
    if not force_update and data_exists_for_date(existing_data, today):
        print(f"[SKIP] Data already exists for {today}. Skipping collection.")
        print("[TIP] Use force_update=true to override")
        
        # Still show summary
        summary = get_data_summary(existing_data)
        print(f"[SUMMARY] Current data summary: {summary}")
        return
    
    # Fetch new data from API
    items, error_msg = fetch_api_data()
    if error_msg:
        print(f"[FAIL] Failed to fetch data: {error_msg}")
        exit(1)
    
    if not items:
        print("[FAIL] No data received from API")
        exit(1)
    
    # Prepare new records
    new_records = prepare_records(items, today)
    print(f"[PREPARE] Prepared {len(new_records)} new records")
    
    # Remove existing data for today (if any) and add new data
    filtered_existing = [item for item in existing_data if item.get('fetch_date') != today]
    all_data = filtered_existing + new_records
    
    # Cleanup old data
    all_data = cleanup_old_data(all_data, days_to_keep=90)
    
    # Save updated data
    if save_data(all_data):
        print("[COMPLETE] Data collection completed successfully!")
        
        # Show summary
        summary = get_data_summary(all_data)
        print(f"[SUMMARY] Updated data summary:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
        
        # Show what was added
        print(f"[NEW] Added {len(new_records)} new records for {today}")
        
    else:
        print("[FAIL] Failed to save data")
        exit(1)

if __name__ == "__main__":
    main() 