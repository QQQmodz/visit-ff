"""
Core Business Logic Services
"""
import os
import sys
import json
import asyncio
import aiohttp
import logging
import threading
import time
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.byte import encrypt_api, Encrypt_ID
from modules.visit_count_pb2 import Info
from api.account_loader import AccountLoader
from api.utils import setup_logging

logger = setup_logging()

# ==================== CONFIGURATION ====================
TOKENS_PER_REQUEST = 20
BATCH_SIZE = 20
MAX_CONCURRENT_REQUESTS = 50
REQUEST_TIMEOUT = 10
TOKEN_REFRESH_INTERVAL = 2 * 60 * 60  # 2 hours

# Get base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_BASE_URL = "https://jwt-gen-vaibhav.vercel.app/token"

# Region configurations
REGIONS = {
    'BD': {'accounts': 'accounts_bd.txt', 'tokens': 'token_bd.json'},
    'IND': {'accounts': 'accounts_ind.txt', 'tokens': 'token_ind.json'},
    'BR': {'accounts': 'accounts_br.txt', 'tokens': 'token_br.json'},
    'US': {'accounts': 'accounts_us.txt', 'tokens': 'token_us.json'},
    'NA': {'accounts': 'accounts_na.txt', 'tokens': 'token_na.json'},
    'SAC': {'accounts': 'accounts_sac.txt', 'tokens': 'token_br.json'},
}

# ==================== TOKEN SERVICE ====================
class TokenService:
    """Manages JWT tokens for all regions"""
    
    def __init__(self):
        self.token_rotation = {}
        self.last_refresh = {}
        self.is_refreshing = False
        self.refresh_lock = threading.Lock()
        self._load_existing_tokens()
    
    def _load_existing_tokens(self):
        """Load tokens from files on startup"""
        for region in REGIONS.keys():
            tokens = self._load_tokens_from_file(region)
            if tokens:
                self.token_rotation[region] = {
                    'all_tokens': tokens,
                    'current_index': 0,
                    'total_tokens': len(tokens)
                }
                logger.info(f"Loaded {len(tokens)} tokens for {region}")
    
    def _load_tokens_from_file(self, region: str) -> List[str]:
        """Load tokens from file"""
        token_file = os.path.join(BASE_DIR, 'tokens', REGIONS[region]['tokens'])
        
        try:
            if not os.path.exists(token_file):
                return []
            
            with open(token_file, 'r') as f:
                data = json.load(f)
            
            tokens = [
                item["token"] for item in data 
                if item.get("token") and len(item["token"]) > 10
            ]
            return tokens
        except Exception as e:
            logger.error(f"Error loading tokens for {region}: {e}")
            return []
    
    def _save_tokens_to_file(self, region: str, tokens: List[Dict]):
        """Save tokens to file"""
        token_file = os.path.join(BASE_DIR, 'tokens', REGIONS[region]['tokens'])
        
        try:
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
            with open(token_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            logger.info(f"Saved {len(tokens)} tokens for {region}")
        except Exception as e:
            logger.error(f"Error saving tokens for {region}: {e}")
    
    def get_tokens(self, region: str, count: int = TOKENS_PER_REQUEST) -> List[str]:
        """Get next batch of tokens using rotation"""
        region = region.upper()
        
        if region not in self.token_rotation:
            tokens = self._load_tokens_from_file(region)
            if not tokens:
                return []
            self.token_rotation[region] = {
                'all_tokens': tokens,
                'current_index': 0,
                'total_tokens': len(tokens)
            }
        
        rotation = self.token_rotation[region]
        all_tokens = rotation['all_tokens']
        total = rotation['total_tokens']
        
        if total == 0:
            return []
        
        current = rotation['current_index']
        end = (current + count) % total
        
        if current < end:
            batch = all_tokens[current:end]
        else:
            batch = all_tokens[current:] + all_tokens[:end]
        
        self.token_rotation[region]['current_index'] = end
        
        return batch
    
    def refresh_region(self, region: str) -> bool:
        """Refresh tokens for a specific region"""
        if self.is_refreshing:
            logger.warning("Refresh already in progress")
            return False
        
        def run_refresh():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._refresh_region_tokens(region))
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_refresh)
        thread.start()
        return True
    
    def refresh_all_regions(self):
        """Refresh tokens for all regions"""
        if self.is_refreshing:
            logger.warning("Refresh already in progress")
            return
        
        def run_refresh():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for region in REGIONS.keys():
                    loop.run_until_complete(self._refresh_region_tokens(region))
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_refresh)
        thread.start()
    
    async def _refresh_region_tokens(self, region: str):
        """Refresh tokens for a specific region (async)"""
        with self.refresh_lock:
            if self.is_refreshing:
                return
            self.is_refreshing = True
        
        try:
            logger.info(f"Refreshing tokens for {region}...")
            
            # Load accounts
            account_loader = AccountLoader()
            accounts = account_loader.load_accounts_for_region(region)
            
            if not accounts:
                logger.warning(f"No accounts found for {region}")
                return
            
            # Fetch tokens
            all_tokens = []
            connector = aiohttp.TCPConnector(
                limit=MAX_CONCURRENT_REQUESTS,
                limit_per_host=30
            )
            
            async with aiohttp.ClientSession(connector=connector) as session:
                for i in range(0, len(accounts), BATCH_SIZE):
                    batch = accounts[i:i + BATCH_SIZE]
                    tasks = [
                        self._fetch_single_token(session, acc, region)
                        for acc in batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in results:
                        if isinstance(result, dict) and result.get('success'):
                            all_tokens.append({
                                'uid': result['uid'],
                                'token': result['token'],
                                'region': region
                            })
                    
                    if i + BATCH_SIZE < len(accounts):
                        await asyncio.sleep(0.2)
            
            # Save tokens
            if all_tokens:
                self._save_tokens_to_file(region, all_tokens)
                
                # Update rotation
                self.token_rotation[region] = {
                    'all_tokens': [t['token'] for t in all_tokens],
                    'current_index': 0,
                    'total_tokens': len(all_tokens)
                }
                self.last_refresh[region] = time.time()
                logger.info(f"Updated {len(all_tokens)} tokens for {region}")
            
        except Exception as e:
            logger.error(f"Error refreshing {region}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self.is_refreshing = False
    
    async def _fetch_single_token(self, session, account: Dict, region: str) -> Dict:
        """Fetch a single JWT token"""
        uid = account['uid']
        password = account['password']
        
        try:
            url = f"{API_BASE_URL}?uid={uid}&password={password}"
            
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ssl=False
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('status') == 'live':
                        token = data.get('token', '')
                        if token and len(token) > 50:
                            return {
                                'success': True,
                                'uid': str(uid),
                                'token': token,
                                'region': data.get('region', region).upper()
                            }
                
                return {
                    'success': False,
                    'uid': str(uid),
                    'error': f"HTTP {resp.status}"
                }
        except Exception as e:
            return {
                'success': False,
                'uid': str(uid),
                'error': str(e)
            }
    
    def get_status(self) -> Dict:
        """Get token status for all regions"""
        status = {
            'is_refreshing': self.is_refreshing,
            'regions': {}
        }
        
        for region in REGIONS.keys():
            token_count = 0
            if region in self.token_rotation:
                token_count = self.token_rotation[region]['total_tokens']
            
            last_refresh = self.last_refresh.get(region, 0)
            
            status['regions'][region] = {
                'tokens_available': token_count > 0,
                'token_count': token_count,
                'last_refresh': time.ctime(last_refresh) if last_refresh else 'Never',
                'minutes_ago': int((time.time() - last_refresh) / 60) if last_refresh else None
            }
        
        return status

# ==================== VISIT SERVICE ====================
class VisitService:
    """Handles sending visits to Free Fire players"""
    
    def __init__(self):
        self.token_service = TokenService()
    
    def get_url(self, region: str) -> str:
        """Get the appropriate API URL for a region"""
        region = region.upper()
        if region == "IND":
            return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif region in {"BR", "US", "SAC", "NA"}:
            return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            return "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    
    def parse_protobuf_response(self, response_data: bytes) -> Optional[Dict]:
        """Parse protobuf response"""
        try:
            info = Info()
            info.ParseFromString(response_data)
            
            return {
                "uid": getattr(info.AccountInfo, 'UID', 0),
                "nickname": getattr(info.AccountInfo, 'PlayerNickname', ""),
                "likes": getattr(info.AccountInfo, 'Likes', 0),
                "region": getattr(info.AccountInfo, 'PlayerRegion', ""),
                "level": getattr(info.AccountInfo, 'Levels', 0)
            }
        except Exception as e:
            logger.error(f"Protobuf parse error: {e}")
            return None
    
    async def send_visits(
        self, 
        tokens: List[str], 
        uid: int, 
        region: str, 
        target: int = 1000
    ) -> Dict:
        """Send visits using multiple tokens"""
        url = self.get_url(region)
        logger.info(f"Sending visits to {uid} in {region} via {url}")
        
        # Build encrypted payload
        try:
            if region == "IND":
                suffix = "1801"
            else:
                suffix = "1801"
            
            encrypt_input = "08" + Encrypt_ID(str(uid)) + suffix
            encrypted = encrypt_api(encrypt_input)
            data = bytes.fromhex(encrypted)
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return {'success': 0, 'failed': target, 'error': str(e)}
        
        total_success = 0
        total_failed = 0
        player_info = None
        start_time = time.time()
        
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=50,
            ttl_dns_cache=300
        )
        
        async with aiohttp.ClientSession(connector=connector) as session:
            while total_success < target:
                remaining = target - total_success
                batch_size = min(remaining, TOKENS_PER_REQUEST)
                
                if not tokens:
                    logger.warning("No tokens available")
                    break
                
                # Build tasks
                tasks = []
                for i in range(batch_size):
                    token = tokens[i % len(tokens)]
                    tasks.append(
                        self._send_single_visit(session, url, token, data)
                    )
                
                # Execute batch
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        total_failed += 1
                        continue
                    
                    success, response = result
                    if success:
                        total_success += 1
                        if player_info is None and response:
                            player_info = self.parse_protobuf_response(response)
                    else:
                        total_failed += 1
                
                # Log progress
                if total_success % 100 == 0 or total_success >= target:
                    logger.info(f"Progress: {total_success}/{target} visits sent")
                
                if total_success < target:
                    await asyncio.sleep(0.05)
        
        elapsed = time.time() - start_time
        
        return {
            'success': total_success,
            'failed': target - total_success,
            'player_info': player_info,
            'time': f"{elapsed:.1f}s"
        }
    
    async def _send_single_visit(
        self, 
        session, 
        url: str, 
        token: str, 
        data: bytes
    ) -> tuple:
        """Send a single visit request"""
        headers = {
            "ReleaseVersion": "OB52",
            "X-GA": "v1 1",
            "Authorization": f"Bearer {token}",
            "Host": url.replace("https://", "").split("/")[0],
            "Content-Type": "application/x-protobuf",
        }
        
        try:
            async with session.post(
                url,
                headers=headers,
                data=data,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    response_data = await resp.read()
                    return True, response_data
                return False, None
        except Exception:
            return False, None
