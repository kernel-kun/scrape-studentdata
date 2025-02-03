import os
import asyncio
import httpx
import random
import logging
from typing import List

class AsyncProxyScraper:
    def __init__(self, 
                 target_url: str, 
                 proxy_sources: List[str],
                 max_concurrent_requests: int = 50,
                 total_requests: int = 10000,
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
                return []  # Return empty list on error
            
            # Gather results from all sources concurrently
            source_results = await asyncio.gather(
                *[fetch_source(source) for source in self.proxy_sources]
            )
            
            # Flatten and deduplicate results
            for result in source_results:
                proxies.extend(result)
        
        # Remove duplicates and filter out potentially invalid proxies
        valid_proxies = list(set(proxy for proxy in proxies if ':' in proxy))
        self.logger.info(f"Fetched {len(valid_proxies)} proxies")
        return valid_proxies

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
        except Exception as e:
            self.logger.debug(f"Proxy {proxy} failed: {e}")
            return False

    async def scrape_with_proxy_rotation(self):
        """
        Main scraping method with async proxy rotation
        """
        # Fetch initial proxies
        proxies = await self.fetch_public_proxies()
        if not proxies:
            self.logger.error("No proxies available. Exiting.")
            return

        # Shuffle proxies to distribute load
        random.shuffle(proxies)

        # Metrics tracking
        successful_requests = 0
        total_attempts = 0

        # Shared asynchronous lock for safe increments
        lock = asyncio.Lock()

        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        async def fetch_with_proxy(proxy):
            nonlocal successful_requests, total_attempts
            
            async with semaphore:
                # Create a dedicated client for each request (due to per-request proxy configuration)
                async with httpx.AsyncClient() as client:
                    success = await self.test_proxy(proxy, client)
                    
                    # Safely update counters using the shared lock
                    async with lock:
                        total_attempts += 1
                        if success:
                            successful_requests += 1
                    
                    return success

        # Limit total number of requests to either total_requests or available proxies
        tasks = [
            fetch_with_proxy(proxy) 
            for proxy in proxies[: min(self.total_requests, len(proxies))]
        ]
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks)
        
        # Log final metrics
        self.logger.info(f"Total Proxy Attempts: {total_attempts}")
        self.logger.info(f"Successful Requests: {successful_requests}")
        if total_attempts > 0:
            self.logger.info(f"Success Rate: {successful_requests / total_attempts * 100:.2f}%")
        else:
            self.logger.info("No proxy attempts were made.")

def main():
    # Fetch configuration from environment variables
    target_url = os.environ.get('TARGET_URL')
    proxy_sources_str = os.environ.get('PROXY_SOURCES', '').strip()
    
    # Split proxy sources, handling pote"ntial empty input
    proxy_sources = [src.strip() for src in proxy_sources_str.split(',') if src.strip()] or [
        'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
        'https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt',
        'https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies_anonymous/http.txt'
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

