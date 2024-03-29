import os
from binance.spot import Spot
import requests
import time

class Binance:
    def __init__(self, app):
        self.app = app
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)

    def account_snapshot(self, user):
        weigth = 10

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
    
    def open_position(self, symbol:str, amount:float):
        weight = 6

        side = 'BUY'
        if amount < 0:
            side = 'SELL'

        response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='MARGIN_BUY')

        return response

    def close_position(self, symbol:str, amount:float):
        weight = 6

        side = 'SELL'
        if amount < 0:
            side = 'BUY'

        response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

        return response
    
    def get_asset_precision(self, symbol:str):
        weight = 20

        response = self.client.exchange_info(symbol=symbol)
        details = response['symbols'][0]
        print(details)
        for symbol_filter in details["filters"]:
            if symbol_filter["filterType"] == "LOT_SIZE":
                step_size = symbol_filter["stepSize"]
                min_quantity = float(symbol_filter["minQty"])
            if symbol_filter["filterType"] == "NOTIONAL":
                min_notional = float(symbol_filter['minNotional'])
            
        return {"stepSize": step_size, "minQty": min_quantity, "minNotional": min_notional}