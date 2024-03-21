import os
from binance.spot import Spot
import time

class Binance:
    def __init__(self):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)

    def account_snapshot(self):
        spot_snapshot = self.client.account_snapshot(type='SPOT')
        time.sleep(0.2)
        margin_snapshot = self.client.account_snapshot(type='MARGIN')
    
        response_data = {}

        # Iterate through balances to find BNB
        for balance in spot_snapshot['snapshotVos'][-1]['data']['balances']:
            if balance['asset'] == 'BNB':
                # Combine free and locked amounts to get total BNB balance
                response_data["BNB_available"] = float(balance['free'])  # + float(balance['locked'])
                break  # Exit loop after finding BNB

        response_data["BTC_balance"] = margin_snapshot['snapshotVos'][-1]['data']['totalNetAssetOfBtc']

        print('spot_snapshot')
        print(spot_snapshot)
        print('margin_snapshot')
        print(margin_snapshot)
        print('response_data')
        print(response_data)

        return response_data