import os
import requests
import random
import time
import logging
from typing import List, Optional

class ProxyScraper:
    def __init__(self,
                 target_url: str,
                 proxy_sources: List[str],
                 max_retries: int = 5,
                 timeout: int = 10):
        """
        Initialize ProxyScraper with configuration parameters

        :param target_url: URL to scrape
        :param proxy_sources: List of URLs to fetch proxy lists
        :param max_retries: Maximum number of retry attempts for a proxy
        :param timeout: Connection timeout in seconds
        """
        self.target_url = target_url
        self.proxy_sources = proxy_sources
        self.max_retries = max_retries
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')

    def fetch_public_proxies(self) -> List[str]:
        """
        Fetch public proxy list from configured sources

        :return: List of proxy servers in format 'ip:port'
        """
        proxies = []
        for source in self.proxy_sources:
            try:
                response = requests.get(source, timeout=self.timeout)
                if response.status_code == 200:
                    proxies.extend(response.text.strip().split('\n'))
            except Exception as e:
                self.logger.warning(f"Error fetching proxies from {source}: {e}")

        # Remove duplicates and filter out potentially invalid proxies
        return list(set(proxy for proxy in proxies if ':' in proxy))

    def test_proxy(self, proxy: str) -> Optional[dict]:
        """
        Test a single proxy

        :param proxy: Proxy in format 'ip:port'
        :return: Working proxy dictionary or None
        """
        proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }

        try:
            response = requests.get(
                self.target_url,
                proxies=proxies,
                timeout=self.timeout
            )
            if response.status_code == 200:
                self.logger.info(f"Proxy {proxy} is working")
                return proxies
        except Exception as e:
            self.logger.warning(f"Proxy {proxy} failed: {e}")

        return None

    def scrape_with_proxy_rotation(self):
        """
        Main scraping method with proxy rotation
        """
        while True:
            # Fetch fresh proxies
            proxies = self.fetch_public_proxies()
            random.shuffle(proxies)

            for proxy in proxies:
                for attempt in range(self.max_retries):
                    try:
                        working_proxy = self.test_proxy(proxy)
                        if working_proxy:
                            # Perform actual scraping here
                            response = requests.get(
                                self.target_url,
                                proxies=working_proxy,
                                timeout=self.timeout
                            )

                            # Process and log the response
                            self.logger.info(f"Successfully scraped {self.target_url} via {proxy}")
                            self.logger.info(f"Response length: {len(response.text)} characters")

                            # Optional: Add your specific parsing logic here
                            break
                    except Exception as e:
                        self.logger.error(f"Scraping attempt {attempt + 1} failed: {e}")

                # Wait between proxy attempts to avoid rate limiting
                time.sleep(random.uniform(1, 3))

            # Wait before next full proxy rotation cycle
            time.sleep(random.uniform(10, 30))

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

    # Initialize and run scraper
    scraper = ProxyScraper(target_url, proxy_sources)
    scraper.scrape_with_proxy_rotation()

if __name__ == '__main__':
    main()
