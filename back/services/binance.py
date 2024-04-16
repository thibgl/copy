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
import numpy as np

class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)


    def aggregate_current_positions(self, group: pd.DataFrame) -> pd.Series:
        result = {}
        for key in group.columns:
            if key in ['netAsset', 'symbol', 'leader_symbol', 'leader_markPrice_AVERAGE']:
                result[key] = group[key].iloc[0]
            else:
                result[key] = group[key].sum()
        return pd.Series(result)

    def handle_current_positions(self, user, dataframe, valueUSDT):
        dataframe.loc[dataframe["leader_LEVERED_RATIO"] > user["account"]["data"]["leverage"], "leader_LEVERED_RATIO"] = user["account"]["data"]["leverage"]
        dataframe["TARGET_SHARE"] = dataframe["leader_WEIGHT_SHARE"] * (dataframe["leader_LEVERED_RATIO"] / dataframe["leader_UNLEVERED_RATIO"] / user["account"]["data"]["leverage"]) * dataframe["leader_LEVERED_POSITION_SHARE"]
        dataframe["TARGET_VALUE"] = valueUSDT * dataframe["TARGET_SHARE"] #* user["account"]["data"]["leverage"]
        dataframe.loc[dataframe["leader_positionAmount_SUM"] < 0, "TARGET_VALUE"] *= -1
        dataframe["TARGET_AMOUNT"] = dataframe["TARGET_VALUE"] / dataframe["leader_markPrice_AVERAGE"]
        dataframe = dataframe.groupby("final_symbol").apply(self.aggregate_current_positions, include_groups=False).reset_index()

        return dataframe

    def validate_amounts(self, dataframe, amount_column, value_column):
        truncated_amount_column = amount_column + "_TRUNCATED"
        dataframe[truncated_amount_column] = dataframe.apply(lambda row: self.truncate_amount(row[amount_column], row["stepSize"]), axis=1)
        dataframe[amount_column + "_PASS"] = (dataframe[value_column].abs() > dataframe["minNotional"]) & (dataframe[truncated_amount_column].abs() > dataframe["minQty"])

        return dataframe
    
    async def user_account_update(self, bot, user, new_positions, user_leaders, new_user_mix, n_leaders): #self, user
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
        # positions.loc[positions.size] = ['SOL',  0.000707,     0.0,   0.00000,  0.000000e+00,  7.073200e-04,  'SOLUSDT']
        print("POSITIONS")
        print(positions)
        print("")
        assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
        valueUSDT = float(self.client.ticker_price("BTCUSDT")["price"]) * assetBTC

        new_positions[["final_symbol", "thousand"]] = new_positions.apply(lambda row: pd.Series([row["symbol"][4:], True] if row["symbol"].startswith('1000') else [row["symbol"], False]), axis=1)
        new_positions.loc[new_positions["thousand"], "markPrice_AVERAGE"] /= 1000
        print("NEW_POSITIONS")
        print(new_positions)
        print("")
        pool = positions[['symbol', 'netAsset']]
        pool = pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_final_symbol", how='outer')
        print("POOL")
        print(pool)
        print("")
        pool["final_symbol"] = pool.apply(lambda row: pd.Series(row["leader_final_symbol"] if isinstance(row["leader_final_symbol"], str) else row["symbol"]), axis=1)
        pool = pool.merge(user_leaders.add_prefix("leader_"), left_on="leader_ID", right_index=True, how='left')
        pool["leader_WEIGHT_SHARE"] = pool["leader_WEIGHT"] / n_leaders
        print("POOL")
        print(pool)
        print("")
        precisions = pd.DataFrame(columns=["stepSize", "minQty", "minNotional"])
        for symbol in pool["final_symbol"].unique():
            symbol, precision = await self.get_symbol_precision(bot, symbol)
            precisions.loc[symbol] = precision
        # print("PRECISIONS")
        # print(precisions)
        # print("")

        pool = pool.merge(precisions, left_on="final_symbol", right_index=True, how='left')
        # print("POOL")
        # print(pool)
        # print("")

        positions_closed = pool[pool["leader_symbol"].isna()].copy()
        if positions_closed.size > 0:
            positions_closed["SYMBOL_PRICE"] = positions_closed["symbol"].apply(lambda symbol: float(self.app.binance.client.ticker_price(symbol)["price"]))
            positions_closed["CURRENT_VALUE"] = positions_closed["netAsset"] * positions_closed["SYMBOL_PRICE"]
            positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE")
            positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("final_symbol")
        print("POSITIONS_CLOSED")
        print(positions_closed)
        print("")

        positions_opened = pool[(pool["symbol"].isna()) & (~pool["leader_symbol"].isna())].copy()
        if positions_opened.size > 0:
            positions_opened = self.handle_current_positions(user, positions_opened, valueUSDT)
            positions_opened = self.validate_amounts(positions_opened, "TARGET_AMOUNT", "TARGET_VALUE")
            positions_opened = positions_opened[positions_opened["TARGET_AMOUNT_PASS"]].set_index("final_symbol")
        print("POSITIONS_OPENED")
        print(positions_opened)
        print("")
        # print(positions_opened["TARGET_VALUE"].abs().sum())
 
        positions_changed = pool[(~pool["symbol"].isna()) & (~pool["leader_symbol"].isna())].copy()
        if positions_changed.size > 0:
            positions_changed = self.handle_current_positions(user, positions_changed, valueUSDT)
            positions_changed["CURRENT_VALUE"] = positions_changed["netAsset"] * positions_changed["leader_markPrice_AVERAGE"]
            positions_changed["DIFF_AMOUNT"] = positions_changed["TARGET_AMOUNT"] - positions_changed["netAsset"]
            positions_changed["DIFF_VALUE"] = positions_changed["TARGET_VALUE"] - positions_changed["CURRENT_VALUE"]
            positions_changed = self.validate_amounts(positions_changed, "netAsset", "CURRENT_VALUE")
            positions_changed = self.validate_amounts(positions_changed, "DIFF_AMOUNT", "DIFF_VALUE")
            positions_changed = self.validate_amounts(positions_changed, "TARGET_AMOUNT", "TARGET_VALUE")
            positions_changed["OPEN"] = (positions_changed["DIFF_AMOUNT"] > 0) & (positions_changed["netAsset"] > 0) | (positions_changed["DIFF_AMOUNT"] < 0) & (positions_changed["netAsset"] < 0) | False
            positions_changed["SWITCH_DIRECTION"] = ((positions_changed["netAsset"] > 0) & (positions_changed["TARGET_AMOUNT"] < 0)) | ((positions_changed["netAsset"] < 0) & (positions_changed["TARGET_AMOUNT"] > 0))
            positions_changed = positions_changed[positions_changed["DIFF_AMOUNT_PASS"]].set_index("final_symbol")
        print("POSITIONS_CHANGED")
        print(positions_changed)
        print("")
    
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
            # "mix": new_user_mix
        }

        return user_account_update, positions_closed, positions_opened, positions_changed, new_user_mix

    
    def user_account_close(self, user, new_user_mix):
        user_account_update = {
            # "account": {
                # "levered_ratio": levered_ratio,
                # "unlevered_ratio": unlevered_ratio,
            # },
            "mix": new_user_mix
        }

        return user_account_update
    
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
        
    def truncate_amount(self, amount, stepSize):
        asset_precision = stepSize.split('1')[0].count('0')
        
        amount = round(amount, asset_precision)

        return amount



    async def get_symbol_precision(self, bot, symbol):
        symbol_precisions = pd.DataFrame(bot["precisions"]["data"])
        
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

            precision = [step_size, min_quantity, min_notional]

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
    


    # def exchange_information(self, bot, symbols):
    #     weigth = 20
        
    #     exchange_data = self.client.exchange_info(symbols=symbols)

    #     symbols = {}

    #     for symbol in exchange_data["symbols"]:
    #         symbols[symbol["symbol"]] = symbol["isMarginTradingAllowed"]

    #     bot["symbols"].update(symbols)

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