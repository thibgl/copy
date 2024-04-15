import os
from binance.spot import Spot
import requests
import time
import json
from urllib.parse import urlencode
import hmac
import hashlib
import traceback
from lib import utils
import pandas as pd


class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)


    def aggregate_current_positions(self, group: pd.DataFrame) -> pd.Series:
        result = {}
        for key in group.columns:
            if key in ['leader_symbol', 'leader_markPrice_AVERAGE']:
                result[key] = group[key].iloc[0]
            else:
                result[key] = group[key].sum()
        return pd.Series(result)

    def handle_current_positions(self, user, df, leaders, valueUSDT):
        # print("DF")
        # print(df)
        # print("")
        # print("LEADERS")
        # print(leaders)
        # print("")
        df = df.merge(leaders.add_prefix("leader_"), left_on="leader_ID", right_index=True, how='inner')
        df["leader_WEIGHT_SHARE"] = df["leader_WEIGHT"] / df.index.unique().size
        df["TARGET_SHARE"] = df["leader_WEIGHT_SHARE"] * df["leader_UNLEVERED_RATIO"] * df["leader_LEVERED_POSITION_SHARE"]
        df["TARGET_VALUE"] = valueUSDT * df["TARGET_SHARE"] * user["account"]["data"]["leverage"]
        df["ABSOLUTE_TARGET_VALUE"] = df["TARGET_VALUE"].abs()
        df["TARGET_AMOUNT"] = df["TARGET_VALUE"] / df["leader_markPrice_AVERAGE"]
        df.loc[df["leader_positionAmount_SUM"] < 0, "TARGET_AMOUNT"] *= -1
        df = df[["leader_symbol", "netAsset", "leader_markPrice_AVERAGE", "TARGET_VALUE", "ABSOLUTE_TARGET_VALUE", "TARGET_AMOUNT"]].groupby("leader_symbol").apply(self.aggregate_current_positions, include_groups=False).reset_index()
        # print(df)
        return df

    def user_account_update(self, user, new_positions, user_leaders, new_user_mix): #self, user
        weigth = 10
        # print("NEW_POSITIONS")
        # print(new_positions)
        # print("")
        # print("USER_LEADERS")
        # print(user_leaders)
        # print("")
        margin_account_data = self.client.margin_account()

        positions = []
        for asset in margin_account_data["userAssets"]:
            amount = float(asset["netAsset"])
            if amount != 0 and asset["asset"] != 'USDT':
                positions.append(asset)

        positions = pd.DataFrame(positions)
        positions = positions.apply(lambda column: column.astype(float) if column.name != 'asset' else column)
        positions["symbol"] = positions["asset"] + 'USDT'
        # print("POSITIONS")
        # print(positions)
        # print("")
        assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
        valueUSDT = float(self.client.ticker_price("BTCUSDT")["price"]) * assetBTC

        pool = positions[['symbol', 'netAsset']]
        pool = pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_symbol", how='outer')
        # print("POOL")
        # print(pool)
        # print("")
        positions_closed = pool[pool["leader_symbol"].isna()]

        # print("POSITIONS_CLOSED")
        # print(positions_closed)
        # print("")

        positions_opened = pool[(pool["symbol"].isna()) & (~pool["leader_symbol"].isna())]
        positions_opened = self.handle_current_positions(user, positions_opened, user_leaders, valueUSDT)
 
        # print("POSITIONS_OPENED")
        # print(positions_opened)
        # print("")

        positions_changed = pool[(~pool["symbol"].isna()) & (~pool["leader_symbol"].isna())]
        positions_changed = self.handle_current_positions(user, positions_changed, user_leaders, valueUSDT)
        positions_changed["DIFF_AMOUNT"] = positions_changed["TARGET_AMOUNT"] - positions_changed["netAsset"]
        positions_changed["CURRENT_VALUE"] = positions_changed["netAsset"] * positions_changed["leader_markPrice_AVERAGE"]
        positions_changed["ABSOLUTE_CURRENT_VALUE"] = positions_changed["CURRENT_VALUE"].abs()
        positions_changed["ABSOLUTE_DIFF_VALUE"] = abs(positions_changed["TARGET_VALUE"] - positions_changed["CURRENT_VALUE"]) * positions_changed["leader_markPrice_AVERAGE"]
        positions_changed["OPEN"] = (positions_changed["DIFF_AMOUNT"] > 0) & (positions_changed["netAsset"] > 0) | (positions_changed["DIFF_AMOUNT"] < 0) & (positions_changed["netAsset"] < 0) | False
        positions_changed["SWITCH_DIRECTION"] = ((positions_changed["netAsset"] > 0) & (positions_changed["TARGET_AMOUNT"] < 0)) | ((positions_changed["netAsset"] < 0) & (positions_changed["TARGET_AMOUNT"] > 0))

        # print("POSITIONS_CHANGED")
        # print(positions_changed)
        # print("")
    
        # pool["UNLEVERED_VALUE"] = pool["LEVERED_VALUE"] / user["account"]["data"]["leverage"]
        # pool["ABSOLUTE_LEVERED_VALUE"] = abs(pool["LEVERED_VALUE"])
        # pool["ABSOLUTE_UNLEVERED_VALUE"] = abs(pool["UNLEVERED_VALUE"])

        # levered_ratio = pool["ABSOLUTE_LEVERED_VALUE"].sum() / valueUSDT
        # unlevered_ratio = pool["ABSOLUTE_UNLEVERED_VALUE"].sum() / valueUSDT

        user_account_update = {
            "account": {
                "value_BTC": assetBTC,
                "value_USDT": valueUSDT,
                # "levered_ratio": levered_ratio,
                # "unlevered_ratio": unlevered_ratio,
                "collateral_margin_level": float(margin_account_data["totalCollateralValueInUSDT"]),
                "collateral_value_USDT": float(margin_account_data["collateralMarginLevel"])

            },
            "positions": positions.set_index("asset").to_dict(),
            "mix": new_user_mix.to_dict()
        }

        return user_account_update, positions_closed[["symbol", "netAsset"]], positions_opened[["leader_symbol", "TARGET_AMOUNT", "ABSOLUTE_TARGET_VALUE"]], positions_changed[["leader_symbol", "netAsset", "ABSOLUTE_CURRENT_VALUE", "TARGET_AMOUNT", "ABSOLUTE_TARGET_VALUE", "DIFF_AMOUNT", "ABSOLUTE_DIFF_VALUE", "OPEN", "SWITCH_DIRECTION"]]

    
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
        

    def exchange_information(self, bot, symbols):
        weigth = 20
        
        exchange_data = self.client.exchange_info(symbols=symbols)

        symbols = {}

        for symbol in exchange_data["symbols"]:
            symbols[symbol["symbol"]] = symbol["isMarginTradingAllowed"]

        bot["symbols"].update(symbols)


    async def get_symbol_precision(self, bot, symbol):
        symbol_precisions = pd.DataFrame(bot["precisions"]["data"])
        thousand = False

        if symbol.startswith('1000'):
            symbol = symbol[4:]
            thousand = True
        
        if symbol in symbol_precisions.index:
            return symbol, symbol_precisions.loc[symbol]
        
        else:
            precision_response = self.client.exchange_info(symbol=symbol)

            details = precision_response['symbols'][0]
            # print(details)
            for symbol_filter in details["filters"]:
                    if symbol_filter["filterType"] == "LOT_SIZE":
                            step_size = symbol_filter["stepSize"]
                            min_quantity = float(symbol_filter["minQty"])
                    if symbol_filter["filterType"] == "NOTIONAL":
                            min_notional = float(symbol_filter['minNotional'])

            precision = [step_size, min_quantity, min_notional, thousand]

            symbol_precisions.loc[symbol] = precision

            precisions_update = {
                    "precisions": symbol_precisions.to_dict()
            }
            await self.app.database.update(obj=bot, update=precisions_update, collection='bot')

            return symbol, symbol_precisions.loc[symbol]   


    async def handle_exception(self, user, error, source, symbol):
        trace = traceback.format_exc()

        await self.app.log.create(user, 'ERROR', f'client/{source}', 'TRADE', f'Error in Binance API: {symbol} - {error}', details=trace)

        return None
    

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


    # def account_snapshot(self, user):
    #     weigth = 10

    #     # assets_lookup = ['USDT', 'BNB']
    #     margin_account_data = self.client.margin_account()
    #     liveAmounts = {}
    #     # print(margin_account_data)
    #     for asset in margin_account_data["userAssets"]:
    #         symbol = asset["asset"]
    #         amount = float(asset["netAsset"])
 
    #         if symbol != 'USDT' and amount != 0:
    #             liveAmounts[symbol + 'USDT'] = amount

    #     # print(liveAmounts)
    #     assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
    #     valueUSDT = float(self.app.binance.client.ticker_price("BTCUSDT")["price"]) * assetBTC

    #     user["liveAmounts"] = liveAmounts
    #     user["valueBTC"] = assetBTC
    #     user["valueUSDT"] = valueUSDT
    #     user["collateralValueUSDT"] = float(margin_account_data["totalCollateralValueInUSDT"])
    #     user["collateralMarginLevel"] = float(margin_account_data["collateralMarginLevel"])

    #     self.app.db.users.update_one({"_id": user["_id"]}, {"$set": {
    #         "liveAmounts": user["liveAmounts"],
    #         "valueBTC": user["valueBTC"],
    #         "valueUSDT": user["valueUSDT"],
    #         "collateralValueUSDT": user["collateralValueUSDT"],
    #         "collateralMarginLevel": user["collateralMarginLevel"]
    #     }})



    # async def close_all_positions(self, user):
    #     user_amounts, user_mix = user["amounts"], user["mix"] 

    #     # doing this way so if we get an error, we don't remove the whole mix & amounts
    #     for symbol, amount in list(user_amounts.items()):
    #         try:
    #             # print(symbol, amount)
    #             response = self.app.binance.close_position(symbol, amount)
    #             # print(response)
    #             user_amounts.pop(symbol)
    #             user_mix.pop(symbol)
    #         except Exception as e:
    #             print(e)
    #             continue
        
    #     live_positions_cursor = self.app.db.live.find({"userId": user["_id"]})
    #     live_positions = await live_positions_cursor.to_list(length=None)
    #     await self.app.db.history.insert_many(live_positions)
    #     await self.app.db.live.delete_many({"userId": user["_id"]})
    #     await self.app.db.users.update_one({"username": "root"}, {"$set": {"mix": user_mix, "amounts": user_amounts}})

    #     # await self.app.log.create(user, source='Binance Service', category='Positions', message='Closed all positions')