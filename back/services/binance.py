import os
from binance.spot import Spot
import time

class Binance:
    def __init__(self, app):
        self.app = app
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)

    def account_snapshot(self, user):
        assets_lookup = ['USDT', 'BNB']
        margin_account_data = self.client.margin_account()

        for asset in margin_account_data["userAssets"]:
            symbol = asset["asset"]
            if symbol in assets_lookup:
                user["account"][symbol] = asset["netAsset"]

        user["account"]["valueBTC"] = margin_account_data["totalNetAssetOfBtc"]
        user["account"]["valueUSDT"] = margin_account_data["totalCollateralValueInUSDT"]

        self.app.db.users.update_one({"username": "root"}, {"$set": {"account": user["account"]}})

        return user["account"]
    
    def open_position(self, asset:str, amount:float, balance:float):
        borrow_response = self.client.margin_max_borrowable(asset=asset)
        response = self.client.margin_borrow(asset=asset, amount=amount)

        return response

    def close_position(self, asset:str, amount:float):
        response = self.client.margin_repay(asset=asset, amount=amount)

        return response