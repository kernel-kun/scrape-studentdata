import os
import asyncio
import httpx
import random
import logging
from typing import List, Optional
from tqdm.asyncio import tqdm
import sys

class AsyncProxyScraper:
    def __init__(self, 
                 target_url: str, 
                 proxy_sources: List[str],
                 max_concurrent_requests: int = 50,
                 total_requests: int = 100000,
                 timeout: float = 10.0):
        """
        Initialize AsyncProxyScraper with configuration parameters
        
        :param target_url: URL to scrape
        :param proxy_sources: List of URLs to fetch proxy lists
        :param max_concurrent_requests: Maximum number of concurrent requests
        :param total_requests: Total number of requests to attempt
        :param timeout: Connection timeout in seconds
        """
        self.target_url = target_url
        self.proxy_sources = proxy_sources
        self.max_concurrent_requests = max_concurrent_requests
        self.total_requests = total_requests
        self.timeout = timeout
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    async def fetch_public_proxies(self) -> List[str]:
        """
        Asynchronously fetch public proxy list from configured sources
        
        :return: List of proxy servers in format 'ip:port'
        """
        proxies = []
        async with httpx.AsyncClient() as client:
            async def fetch_source(source):
                try:
                    response = await client.get(source, timeout=self.timeout)
                    if response.status_code == 200:
                        return response.text.strip().split('\n')
                except Exception as e:
                    self.logger.warning(f"Error fetching proxies from {source}: {e}")
                    return []
            
            # Gather results from all sources concurrently
            source_results = await asyncio.gather(
                *[fetch_source(source) for source in self.proxy_sources]
            )
            
            # Flatten and deduplicate results
            for result in source_results:
                proxies.extend(result)
        
        # Remove duplicates and filter out potentially invalid proxies
        return list(set(proxy for proxy in proxies if ':' in proxy))

    async def test_proxy(self, proxy: str, client: httpx.AsyncClient) -> bool:
        """
        Test a single proxy
        
        :param proxy: Proxy in format 'ip:port'
        :param client: Async HTTP client
        :return: True if proxy works, False otherwise
        """
        proxies = {
            'http://': f'http://{proxy}',
            'https://': f'http://{proxy}'
        }
        
        try:
            response = await client.get(
                self.target_url, 
                proxies=proxies, 
                timeout=self.timeout
            )
            return response.status_code == 200
        except Exception:
            return False

    async def scrape_with_proxy_rotation(self):
        """
        Main scraping method with async proxy rotation and tqdm progress tracking
        """
        # Fetch initial proxies
        proxies = await self.fetch_public_proxies()
        
        # Shuffle to distribute load
        random.shuffle(proxies)
        
        # Limit proxies to total requested
        proxies = proxies[:self.total_requests]
        
        # Metrics tracking with thread-safe counters
        successful_requests = 0
        
        # Create a thread-safe async lock
        lock = asyncio.Lock()
        
        # Create tqdm progress bar
        progress_bar = tqdm(
            total=len(proxies), 
            desc="Proxy Testing", 
            unit="proxy",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            file=sys.stdout
        )
        
        async def fetch_with_proxy(proxy):
            nonlocal successful_requests
            
            try:
                async with httpx.AsyncClient() as client:
                    success = await self.test_proxy(proxy, client)
                    
                    # Update metrics and progress bar
                    async with lock:
                        if success:
                            successful_requests += 1
                        progress_bar.update(1)
                    
                    return success
            except Exception:
                async with lock:
                    progress_bar.update(1)
                return False
        
        # Run all tasks concurrently
        await asyncio.gather(*[fetch_with_proxy(proxy) for proxy in proxies])
        
        # Close progress bar
        progress_bar.close()
        
        # Final metrics display
        print("\n--- Proxy Scraping Summary ---")
        print(f"Total Proxies Tested: {len(proxies)}")
        print(f"Successful Proxies: {successful_requests}")
        print(f"Success Rate: {successful_requests/len(proxies)*100:.2f}%")
        
        # Optional: Return metrics for potential further processing
        return {
            'total_proxies': len(proxies),
            'successful_proxies': successful_requests,
            'success_rate': successful_requests/len(proxies)*100
        }

def main():
    # Fetch configuration from environment variables
    target_url = os.environ.get('TARGET_URL')
    proxy_sources_str = os.environ.get('PROXY_SOURCES', '').strip()


    # Split proxy sources, handling pote"ntial empty input
    proxy_sources = [src.strip() for src in proxy_sources_str.split(',') if src.strip()] or [
        'https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt','https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies_anonymous/http.txt','https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'
    ]
    
    # Validate target URL
    if not target_url:
        raise ValueError("TARGET_URL environment variable must be set")
    
    # Initialize scraper
    scraper = AsyncProxyScraper(
        target_url, 
        proxy_sources, 
        max_concurrent_requests=50,  # Adjust based on your needs
        total_requests=100  # Adjust based on your needs
    )
    
    # Run the async scraper
    asyncio.run(scraper.scrape_with_proxy_rotation())

if __name__ == '__main__':
    main()
