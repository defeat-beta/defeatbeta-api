import logging
import unittest
import threading

from defeatbeta_api.data.ticker import Ticker

class TestTickerMultithreaded(unittest.TestCase):

    def test_info(self):
        def run_test():
            ticker = Ticker("BABA", http_proxy="http://127.0.0.1:33210", log_level=logging.DEBUG)
            result = ticker.info()
            print(f"Thread {threading.current_thread().name} result:\n{result.to_string()}")
            result = ticker.download_data_performance()
            print(result)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=run_test, name=f"TestThread-{i}")
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()