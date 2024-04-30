import os
from binance.spot import Spot
from urllib.parse import urlencode
import traceback
from lib import utils
import pandas as pd
import math
from decimal import Decimal, ROUND_DOWN

thousand_ignore = ["1000SATSUSDT"]

class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)


    def validate_amounts(self, dataframe, amount_column, value_column):
        truncated_amount_column = amount_column + "_TRUNCATED"
        dataframe[truncated_amount_column] = dataframe.apply(lambda row: self.truncate_amount(row[amount_column], row["stepSize"]), axis=1)
        dataframe[amount_column + "_PASS"] = (dataframe[value_column].abs() > dataframe["minNotional"] * 1.05) & (dataframe[truncated_amount_column].abs() > dataframe["minQty"])

        return dataframe
    
    async def get_precisions(self, bot, dataframe):
        precisions = pd.DataFrame(columns=["stepSize", "minQty", "minNotional"])

        for symbol in dataframe["final_symbol"].unique():
            symbol, precision = await self.get_symbol_precision(bot, symbol)
            precisions.loc[symbol] = precision

        dataframe = dataframe.merge(precisions, left_on="final_symbol", right_index=True, how='left')

        return dataframe
    
    async def format_closed_positions(self, bot, closed_positions):
        closed_positions["SYMBOL_PRICE"] = closed_positions["symbol"].apply(lambda symbol: float(self.app.binance.client.ticker_price(symbol)["price"]))
        closed_positions["CURRENT_VALUE"] = closed_positions["netAsset"] * closed_positions["SYMBOL_PRICE"]

        closed_positions = await self.get_precisions(bot, closed_positions)
        closed_positions = self.validate_amounts(closed_positions, "netAsset", "CURRENT_VALUE")

        closed_positions = closed_positions[closed_positions["netAsset_PASS"]].set_index("final_symbol")

        return closed_positions

    async def user_account_update(self, bot, user, new_positions, user_leaders, mix_diff): #self, user
        weigth = 10
        try:

            margin_account_data = self.client.margin_account()

            positions = pd.DataFrame(margin_account_data["userAssets"])
            for column in positions.columns:
                if column != 'asset':
                    positions[column] = positions[column].astype(float)
            positions = positions.loc[(positions["asset"] != 'USDT') & (positions["netAsset"] != 0)]
            positions["symbol"] = positions["asset"] + 'USDT'

            assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
            valueUSDT = float(self.client.ticker_price("BTCUSDT")["price"]) * assetBTC
            collateral_margin_level = float(margin_account_data["totalCollateralValueInUSDT"])
            pool = positions[['symbol', 'netAsset']]

            if len(new_positions) > 0:
                new_positions[["final_symbol", "thousand"]] = new_positions.apply(lambda row: pd.Series([row["symbol"][4:], True] if row["symbol"].startswith('1000') and row["symbol"] not in thousand_ignore else [row["symbol"], False]), axis=1)
                new_positions.loc[new_positions["thousand"], "markPrice_AVERAGE"] /= 1000

                pool = pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_final_symbol", how='outer')
                pool["final_symbol"] = pool.apply(lambda row: pd.Series(row["leader_final_symbol"] if isinstance(row["leader_final_symbol"], str) else row["symbol"]), axis=1)
                pool = pool.merge(user_leaders.add_prefix("leader_"), left_on="leader_ID", right_index=True, how='left')
                active_leaders = pool["leader_ID"].dropna().unique()
                n_leaders = active_leaders.size

                print(f'[{utils.current_readable_time()}]: Updating Positions for {n_leaders} leaders')

                positions_closed = pool.copy()[pool["leader_symbol"].isna()]
                if len(positions_closed) > 0:
                    positions_closed = await self.format_closed_positions(bot, positions_closed)

                positions_opened_changed = pool.copy()[~pool["leader_symbol"].isna()]
                if len(positions_opened_changed) > 0:
                    user_leverage = user["account"]["data"]["leverage"]

                    positions_opened_changed["INVESTED_RATIO"] = positions_opened_changed["leader_LEVERED_RATIO"]
                    positions_opened_changed.loc[positions_opened_changed["INVESTED_RATIO"] > 1, "INVESTED_RATIO"] = 1
                    positions_opened_changed.loc[:, "INVESTED_RATIO_BOOSTED"] = positions_opened_changed["INVESTED_RATIO"] * (1 + (1 - positions_opened_changed["INVESTED_RATIO"]) ** (2 - positions_opened_changed["INVESTED_RATIO"]))

                    positions_opened_changed.loc[positions_opened_changed["leader_TICKS"] < 100, "leader_AVERAGE_LEVERED_RATIO"] = 0.1
                    positions_opened_changed.loc[positions_opened_changed["leader_AVERAGE_LEVERED_RATIO"] > 1, "leader_AVERAGE_LEVERED_RATIO"] = 1
                    positions_opened_changed["MIX_SHARE"] = positions_opened_changed["leader_LEVERED_POSITION_SHARE"] * positions_opened_changed["leader_WEIGHT"] * positions_opened_changed["leader_AVERAGE_UNLEVERED_RATIO"] * positions_opened_changed["leader_AVERAGE_LEVERAGE"]
                    positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["MIX_SHARE"] / positions_opened_changed["MIX_SHARE"].sum()

                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * valueUSDT * user["detail"]["data"]["TARGET_RATIO"] * user_leverage * positions_opened_changed["INVESTED_RATIO_BOOSTED"]
                    positions_opened_changed.loc[positions_opened_changed["leader_positionAmount_SUM"] < 0, "TARGET_VALUE"] *= -1

                    # print(positions_opened_changed)
                    # print(positions_opened_changed["TARGET_VALUE"].abs().sum())
                    # print(positions_opened_changed["TARGET_VALUE_TEST"].abs().sum())

                    if n_leaders == user["account"]["data"]["n_leaders"] and collateral_margin_level > 1.25 and not (positions_opened_changed['leader_TICKS'] == 100).any():
                        positions_opened_changed = positions_opened_changed[positions_opened_changed["leader_symbol"].isin(mix_diff) | positions_opened_changed["symbol"].isna()]

                if len(positions_opened_changed) > 0:
                    positions_opened_changed = positions_opened_changed.groupby("final_symbol").agg({
                        "symbol": 'last',
                        "netAsset": 'last',
                        "leader_markPrice_AVERAGE": 'mean',
                        "leader_ID": 'unique',
                        "leader_WEIGHT": 'sum',
                        "leader_LEVERED_POSITION_SHARE": 'sum',
                        "MIX_SHARE": 'sum',
                        "TARGET_SHARE": 'sum',
                        "TARGET_VALUE": 'sum'
                        }).reset_index()
                    positions_opened_changed['leader_ID'] = positions_opened_changed['leader_ID'].astype(str)
                    
                    positions_opened_changed["TARGET_AMOUNT"] = positions_opened_changed["TARGET_VALUE"] / positions_opened_changed["leader_markPrice_AVERAGE"]

                    positions_opened_changed = await self.get_precisions(bot, positions_opened_changed)
                    positions_opened_changed = self.validate_amounts(positions_opened_changed, "TARGET_AMOUNT", "TARGET_VALUE")
                    # print(positions_opened_changed)
                    # print(positions_opened_changed["TARGET_VALUE"].abs().sum())
                    positions_opened_changed = positions_opened_changed[positions_opened_changed["TARGET_AMOUNT_PASS"]]

                positions_opened = positions_opened_changed.copy()[positions_opened_changed["symbol"].isna()].set_index("final_symbol")
                
                positions_changed = positions_opened_changed.copy()[~positions_opened_changed["symbol"].isna()]
                if len(positions_changed) > 0:
                    positions_changed["CURRENT_VALUE"] = positions_changed["netAsset"] * positions_changed["leader_markPrice_AVERAGE"]
                    positions_changed["DIFF_AMOUNT"] = positions_changed["TARGET_AMOUNT"] - positions_changed["netAsset"]
                    positions_changed["DIFF_VALUE"] = positions_changed["TARGET_VALUE"] - positions_changed["CURRENT_VALUE"]

                    positions_changed["OPEN"] = ((positions_changed["DIFF_AMOUNT"] > 0) & (positions_changed["TARGET_AMOUNT"] > 0)) | ((positions_changed["DIFF_AMOUNT"] < 0) & (positions_changed["TARGET_AMOUNT"] < 0))
                    positions_changed["SWITCH_DIRECTION"] = ((positions_changed["netAsset"] > 0) & (positions_changed["TARGET_AMOUNT"] < 0)) | ((positions_changed["netAsset"] < 0) & (positions_changed["TARGET_AMOUNT"] > 0))
                    positions_changed["DIFF_VALUE_ABS"] = positions_changed["DIFF_VALUE"].abs()

                    positions_changed = self.validate_amounts(positions_changed, "netAsset", "CURRENT_VALUE")
                    positions_changed = self.validate_amounts(positions_changed, "DIFF_AMOUNT", "DIFF_VALUE")
                    positions_changed = positions_changed.sort_values(by=["DIFF_VALUE_ABS"], ascending=False)
                    positions_changed = positions_changed[positions_changed["DIFF_AMOUNT_PASS"]].set_index("final_symbol")
            else:
                print(f'[{utils.current_readable_time()}]: Updating Positions')

                positions_closed = pool.copy()
                positions_closed["final_symbol"] = positions_closed["symbol"]
                positions_closed = await self.format_closed_positions(bot, positions_closed)
                
                positions_opened = []
                positions_changed = []
                n_leaders = 0
                active_leaders = []

            user_account_update = {
                "account": {
                    "value_BTC": assetBTC,
                    "value_USDT": valueUSDT,
                    # "levered_ratio": levered_ratio,
                    # "unlevered_ratio": unlevered_ratio,
                    "collateral_margin_level": collateral_margin_level,
                    "collateral_value_USDT": float(margin_account_data["collateralMarginLevel"]),
                    "n_leaders": n_leaders,
                    "active_leaders": list(active_leaders)
                },
                "positions": positions.set_index("asset").to_dict(),
                # "mix": new_user_mix
            }

            return user_account_update, positions_closed, positions_opened, positions_changed


        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_update', None)


    async def user_account_close(self, bot, user, new_user_mix):
        try:
            user_account_update = {
                # "account": {
                    # "levered_ratio": levered_ratio,
                    # "unlevered_ratio": unlevered_ratio,
                # },
                "mix": new_user_mix
            }

            return user_account_update
        
        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_close', None)
    
    
    async def open_position(self, user, symbol:str, amount:float):
        # weight = 6
# 
        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='MARGIN_BUY')
            
            return response

        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.':
                print('Account has insufficient balance for requested action.')

                response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

                return response
                

    async def close_position(self, user, symbol:str, amount:float):
        # weight = 6

        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_REPAY')

            return response
        
        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.':
                print('Account has insufficient balance for requested action.')

                response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

                return response
        
    def truncate_amount(self, amount, stepSize):
        # decimals = stepSize.split('1')[0].count('0')

        # multiplier = 10 ** decimals if decimals > 0 else 1
        # final_amount = math.floor(abs(amount) * multiplier) / multiplier
        # return final_amount if amount >= 0 else -final_amount

        # final_amount = round(amount, decimals)
        # return final_amount

        amount = Decimal(amount)
        decimals = Decimal(stepSize)
        truncated = (amount // decimals) * decimals
        return float(truncated.quantize(decimals, rounding=ROUND_DOWN))
    
    async def get_symbol_precision(self, bot, symbol):
        try:

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

        except Exception as e:
            await self.handle_exception(bot, bot, e, 'get_symbol_precision', None)


    async def handle_exception(self, bot, user, error, source, symbol):
        trace = traceback.format_exc()

        await self.app.log.create(bot, user, 'ERROR', f'client/{source}', 'TRADE', f'Error in Binance API: {symbol} - {error}', details=trace)

        pass
    


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