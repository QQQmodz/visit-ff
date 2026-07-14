"""
Account Loading and Processing
"""
import os
import sys
import logging
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.simplify import AccountSimplifier

logger = logging.getLogger(__name__)

class AccountLoader:
    """Load and process account files"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.simplifier = AccountSimplifier()
    
    def load_accounts_for_region(self, region: str) -> List[Dict]:
        """Load and process accounts for a specific region"""
        region = region.upper()
        
        # Map region to file
        region_files = {
            'BD': 'accounts_bd.txt',
            'IND': 'accounts_ind.txt',
            'BR': 'accounts_br.txt',
            'US': 'accounts_us.txt',
            'NA': 'accounts_na.txt',
            'SAC': 'accounts_sac.txt',
        }
        
        if region not in region_files:
            logger.error(f"Unknown region: {region}")
            return []
        
        filepath = os.path.join(self.base_dir, 'accounts', region_files[region])
        
        # Process file through simplifier
        accounts = self.simplifier.process_file(filepath)
        
        # Add region to each account
        for acc in accounts:
            acc['region'] = region
        
        logger.info(f"Loaded {len(accounts)} accounts for {region}")
        return accounts
    
    def load_all_accounts(self) -> Dict[str, List[Dict]]:
        """Load accounts for all regions"""
        result = {}
        for region in ['BD', 'IND', 'BR', 'US', 'NA', 'SAC']:
            accounts = self.load_accounts_for_region(region)
            if accounts:
                result[region] = accounts
        return result
