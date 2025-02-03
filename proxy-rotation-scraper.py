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
                 timeout: float = 10.0,
                 sleep_interval: float = 5.0):
        """
        Initialize AsyncProxyScraper with configuration parameters.

        :param target_url: URL to scrape
        :param proxy_sources: List of URLs to fetch proxy lists
        :param max_concurrent_requests: Maximum number of concurrent requests
        :param timeout: Connection timeout in seconds
        :param sleep_interval: Time (in seconds) to wait between cycles
        """
        self.target_url = target_url
        self.proxy_sources = proxy_sources
        self.max_concurrent_requests = max_concurrent_requests
        self.timeout = timeout
        self.sleep_interval = sleep_interval
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        # Overall metrics
        self.total_attempts = 0
        self.successful_requests = 0
        self.lock = asyncio.Lock()  # Shared lock for metric updates

    async def fetch_public_proxies(self) -> List[str]:
        """
        Asynchronously fetch public proxy list from configured sources.

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
        Test a single proxy.

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

    async def run_cycle(self):
        """
        Run one cycle: fetch proxies, test them concurrently,
        and update metrics.
        """
        proxies = await self.fetch_public_proxies()
        if not proxies:
            self.logger.error("No proxies available this cycle.")
            return

        # Shuffle proxies to distribute load
        random.shuffle(proxies)

        semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        async def fetch_with_proxy(proxy):
            async with semaphore:
                async with httpx.AsyncClient() as client:
                    success = await self.test_proxy(proxy, client)
                    async with self.lock:
                        self.total_attempts += 1
                        if success:
                            self.successful_requests += 1
                    return success

        # Schedule tasks for each proxy
        tasks = [fetch_with_proxy(proxy) for proxy in proxies]
        await asyncio.gather(*tasks)

    async def scrape_with_proxy_rotation(self):
        """
        Continuously perform proxy testing cycles and print metrics.
        """
        while True:
            # Run one full cycle of fetching and testing proxies
            await self.run_cycle()
            
            # Log metrics for this cycle
            async with self.lock:
                self.logger.info(f"Total Attempts: {self.total_attempts} | "
                                 f"Successful Requests: {self.successful_requests} | "
                                 f"Success Rate: {self.successful_requests / self.total_attempts * 100:.2f}%")
            
            # Wait before starting the next cycle
            await asyncio.sleep(self.sleep_interval)

def main():
    # Fetch configuration from environment variables
    target_url = os.environ.get('TARGET_URL')
    proxy_sources_str = os.environ.get('PROXY_SOURCES', '').strip()
    
    # Split proxy sources, handling potential empty input
    proxy_sources = [src.strip() for src in proxy_sources_str.split(',') if src.strip()] or [
        'https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/http.txt',
        'https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies_anonymous/http.txt',
        'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'
    ]
    
    # Validate target URL
    if not target_url:
        raise ValueError("TARGET_URL environment variable must be set")
    
    # Initialize scraper with continuous mode parameters
    scraper = AsyncProxyScraper(
        target_url, 
        proxy_sources, 
        max_concurrent_requests=50,  # Adjust as needed
        timeout=10.0,
        sleep_interval=5.0  # Time to wait between cycles
    )
    
    # Run the async scraper continuously
    asyncio.run(scraper.scrape_with_proxy_rotation())

if __name__ == '__main__':
    main()
