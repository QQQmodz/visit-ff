"""
Account Simplifier - Processes account files
Extracts UID and password from various formats
"""
import os
import json
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class AccountSimplifier:
    """Simplifies account files to extract UID and password"""
    
    def process_file(self, filepath: str) -> List[Dict]:
        """Process an account file and extract UID:password pairs"""
        accounts = []
        
        if not os.path.exists(filepath):
            logger.warning(f"File not found: {filepath}")
            return []
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Try JSON first
            accounts = self._extract_from_json(content)
            
            # If no accounts found, try line-by-line
            if not accounts:
                accounts = self._extract_from_lines(content)
            
            # Filter and validate
            valid_accounts = []
            for acc in accounts:
                uid = acc.get('uid', '')
                password = acc.get('password', '')
                
                if not uid or not password:
                    continue
                
                # Clean UID (digits only)
                uid_clean = ''.join(filter(str.isdigit, str(uid)))
                
                if len(uid_clean) >= 5 and len(password) >= 1:
                    valid_accounts.append({
                        'uid': uid_clean,
                        'password': password.strip()
                    })
            
            logger.info(f"Extracted {len(valid_accounts)} valid accounts from {filepath}")
            return valid_accounts
            
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            return []
    
    def _extract_from_json(self, content: str) -> List[Dict]:
        """Extract accounts from JSON content"""
        accounts = []
        
        try:
            data = json.loads(content)
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        uid = self._find_value(item, ['uid', 'UID', 'userId', 'id'])
                        password = self._find_value(item, ['password', 'pass', 'pwd'])
                        
                        if uid and password:
                            accounts.append({'uid': str(uid), 'password': str(password)})
            
            elif isinstance(data, dict):
                uid = self._find_value(data, ['uid', 'UID', 'userId', 'id'])
                password = self._find_value(data, ['password', 'pass', 'pwd'])
                
                if uid and password:
                    accounts.append({'uid': str(uid), 'password': str(password)})
                    
        except json.JSONDecodeError:
            pass
        
        return accounts
    
    def _extract_from_lines(self, content: str) -> List[Dict]:
        """Extract accounts from line-by-line format"""
        accounts = []
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Try various separators
            uid, password = None, None
            
            for sep in [':', ';', '|', '=', '\t']:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        uid = parts[0].strip()
                        password = parts[1].strip()
                        break
            
            # Try space if no separator found
            if not uid and ' ' in line:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    uid, password = parts[0].strip(), parts[1].strip()
            
            if uid and password:
                accounts.append({'uid': uid, 'password': password})
        
        return accounts
    
    def _find_value(self, data: Dict, keys: List[str]) -> Optional[str]:
        """Find a value by trying multiple keys"""
        for key in keys:
            if key in data and data[key]:
                return data[key]
        return None
