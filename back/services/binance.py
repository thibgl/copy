import os
from binance.spot import Spot
import requests
import time
import json
from urllib.parse import urlencode
import hmac
import hashlib
import traceback

class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)

        # self.servertimeint = None
        # self.hashedsig = None
        # self.request_server_time()

    # def request_server_time(self):
    #     servertime = requests.get("https://api.binance.com/api/v1/time")
    #     servertimeobject = json.loads(servertime.text)
    #     self.servertimeint = servertimeobject['serverTime']
    #     self.hashedsig = hmac.new(self.BINANCE_SECRET_KEY.encode(), urlencode({
    #             "timestamp" : self.servertimeint,
    #         }).encode(), hashlib.sha256).hexdigest()

    # def request_binance_no_wrapper(self):
    #     userdata = requests.get("https://api.binance.com/sapi/v1/margin/account",
    #         params = {
    #             "signature" : self.hashedsig,
    #             "timestamp" : self.servertimeint,
    #         },
    #         headers = {
    #             "X-MBX-APIKEY" : self.BINANCE_API_KEY,
    #         }
    #     )
    #     print(userdata)
    def exchange_information(self, bot, symbols):
        weigth = 20
        
        exchange_data = self.client.exchange_info(symbols=symbols)

        symbols = {}

        for symbol in exchange_data["symbols"]:
            symbols[symbol["symbol"]] = symbol["isMarginTradingAllowed"]

        print(symbols)
        bot["symbols"].update(symbols)


    def account_snapshot(self, user):
        weigth = 10

        assets_lookup = ['USDT', 'BNB']
        margin_account_data = self.client.margin_account()
        liveAmounts = {}
        # print(margin_account_data)
        for asset in margin_account_data["userAssets"]:
            symbol = asset["asset"]
            amount = float(asset["netAsset"])
 
            if symbol != 'USDT' and amount != 0:
                liveAmounts[symbol + 'USDT'] = amount

        # print(liveAmounts)
        assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
        valueUSDT = float(self.app.binance.client.ticker_price("BTCUSDT")["price"]) * assetBTC

        user["liveAmounts"] = liveAmounts
        user["valueBTC"] = assetBTC
        user["valueUSDT"] = valueUSDT
        user["collateralValueUSDT"] = float(margin_account_data["totalCollateralValueInUSDT"])
        user["collateralMarginLevel"] = float(margin_account_data["collateralMarginLevel"])

        # self.app.db.users.update_one({"username": "root"}, {"$set": {"account": user["account"]}})
    
    async def open_position(self, user, symbol:str, amount:float):
        weight = 6

        # try:
        side = 'BUY'
        if amount < 0:
            side = 'SELL'

        response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='MARGIN_BUY')
        
        return response

        # except Exception as e:
        #     await self.handle_exception(user, e, 'open_position', symbol)
            

    async def close_position(self, user, symbol:str, amount:float):
        weight = 6

        # try:
        side = 'BUY'
        if amount < 0:
            side = 'SELL'

        response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

        return response
        
        # except Exception as e:
        #     await self.handle_exception(user, e, 'close_position', symbol)
        

    def get_asset_precision(self, symbol:str, thousand=False):
        weight = 20

        response = self.client.exchange_info(symbol=symbol)
        details = response['symbols'][0]
        # print(details)
        for symbol_filter in details["filters"]:
            if symbol_filter["filterType"] == "LOT_SIZE":
                step_size = symbol_filter["stepSize"]
                min_quantity = float(symbol_filter["minQty"])
            if symbol_filter["filterType"] == "NOTIONAL":
                min_notional = float(symbol_filter['minNotional'])
            
        return {"stepSize": step_size, "minQty": min_quantity, "minNotional": min_notional, "thousand": thousand}
    

    async def close_all_positions(self, user):
        user_amounts, user_mix = user["amounts"], user["mix"] 

        # doing this way so if we get an error, we don't remove the whole mix & amounts
        for symbol, amount in list(user_amounts.items()):
            try:
                # print(symbol, amount)
                response = self.app.binance.close_position(symbol, amount)
                # print(response)
                user_amounts.pop(symbol)
                user_mix.pop(symbol)
            except Exception as e:
                print(e)
                continue
        
        live_positions_cursor = self.app.db.live.find({"userId": user["_id"]})
        live_positions = await live_positions_cursor.to_list(length=None)
        await self.app.db.history.insert_many(live_positions)
        await self.app.db.live.delete_many({"userId": user["_id"]})
        await self.app.db.users.update_one({"username": "root"}, {"$set": {"mix": user_mix, "amounts": user_amounts}})

        # await self.app.log.create(user, source='Binance Service', category='Positions', message='Closed all positions')

    async def handle_exception(self, user, error, source, symbol):
        trace = traceback.format_exc()

        await self.app.log.create(user, 'ERROR', f'client/{source}', 'TRADE', f'Error in Binance API: {symbol} - {error}', details=trace)

        return None