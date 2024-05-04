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


    def validate_amounts(self, dataframe, amount_column, value_column, price_column):
        truncated_amount_column = amount_column + "_TRUNCATED"
        dataframe[truncated_amount_column] = dataframe.apply(lambda row: self.truncate_amount(row[amount_column], row["stepSize"]), axis=1)
        dataframe[amount_column + "_PASS"] = (dataframe[value_column].abs() > dataframe["minNotional"] * 1.05) & (dataframe[truncated_amount_column].abs() > dataframe["minQty"])
        dataframe["MIN_AMOUNT"] = (dataframe["minNotional"] / dataframe[price_column]).combine(dataframe["minQty"] * (dataframe["minNotional"] / dataframe[price_column]), max) * 1.05

        return dataframe
    
    async def get_precisions(self, bot, dataframe):
        precisions = pd.DataFrame(columns=["stepSize", "minQty", "minNotional"])

        for symbol in dataframe["final_symbol"].unique():
            symbol, precision = await self.get_symbol_precision(bot, symbol)
            precisions.loc[symbol] = precision

        dataframe = dataframe.merge(precisions, left_on="final_symbol", right_index=True, how='left')

        return dataframe
    
    async def get_symbol_prices(self, bot, dataframe):
        dataframe["SYMBOL_PRICE"] = dataframe.apply(lambda row: float(self.app.binance.client.ticker_price(row["symbol"])["price"]), axis=1)
        dataframe["CURRENT_VALUE"] = dataframe["netAsset"] * dataframe["SYMBOL_PRICE"]

        return dataframe

    async def user_account_update(self, bot, user, new_positions, user_leaders, mix_diff, lifecycle): #self, user
        weigth = 10
        try:
            margin_account_data = self.client.margin_account()

            assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
            valueUSDT = float(self.client.ticker_price("BTCUSDT")["price"]) * assetBTC
            collateral_margin_level = float(margin_account_data["totalCollateralValueInUSDT"])

            user_positions = pd.DataFrame(margin_account_data["userAssets"])
            for column in user_positions.columns:
                if column != 'asset':
                    user_positions[column] = user_positions[column].astype(float)
            user_positions = user_positions.loc[(user_positions["netAsset"] != 0)]
            user_positions["symbol"] = user_positions["asset"] + 'USDT'

            pool = user_positions[['asset', 'symbol', 'netAsset', 'borrowed', 'free']]
            live_pool = pool.copy().loc[pool["asset"] != 'USDT']

            if len(new_positions) > 0:
                new_positions[["final_symbol", "thousand"]] = new_positions.apply(lambda row: pd.Series([row["symbol"][4:], True] if row["symbol"].startswith('1000') and row["symbol"] not in thousand_ignore else [row["symbol"], False]), axis=1)
                new_positions.loc[new_positions["thousand"], "markPrice"] /= 1000

                live_pool = live_pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_final_symbol", how='outer')
                live_pool["final_symbol"] = live_pool.apply(lambda row: pd.Series(row["leader_final_symbol"] if isinstance(row["leader_final_symbol"], str) else row["symbol"]), axis=1)
                live_pool = live_pool.merge(user_leaders.add_prefix("user_"), left_on="leader_ID", right_index=True, how='left')
                live_pool = await self.get_precisions(bot, live_pool)

                active_leaders = live_pool["leader_ID"].dropna().unique()
                n_leaders = active_leaders.size

                print(f'[{utils.current_readable_time()}]: Updating Positions for {n_leaders} leaders')

                positions_closed = live_pool.copy()[live_pool["leader_symbol"].isna()]
                if len(positions_closed) > 0:
                    positions_closed = await self.get_symbol_prices(bot, positions_closed)
                    positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE", "SYMBOL_PRICE")
                    positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")

                positions_opened_changed = live_pool.copy()[~live_pool["leader_symbol"].isna()]
                if len(positions_opened_changed) > 0:
                    user_leverage = user["account"]["data"]["leverage"] - 1

                    positions_opened_changed.loc[positions_opened_changed["leader_AVERAGE_LEVERAGE"] > user_leverage,"SCALED_LEVERAGE"] = 2 - (user_leverage / positions_opened_changed["leader_AVERAGE_LEVERAGE"])
                    positions_opened_changed.loc[positions_opened_changed["leader_AVERAGE_LEVERAGE"] <= user_leverage,"SCALED_LEVERAGE"] = user_leverage / positions_opened_changed["leader_AVERAGE_LEVERAGE"]

                    positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["leader_POSITION_SHARE"] * positions_opened_changed["leader_INVESTED_RATIO"] * positions_opened_changed["SCALED_LEVERAGE"] * positions_opened_changed["user_WEIGHT"] * user["detail"]["data"]["LEADER_CAP"] / 2
                    positions_opened_changed.loc[positions_opened_changed["leader_positionAmount"] < 0, "TARGET_SHARE"] *= -1

                    # print(positions_opened_changed)

                    positions_opened_changed = positions_opened_changed.groupby("final_symbol").agg({
                        "symbol": 'first',
                        "leader_symbol": 'first',
                        "netAsset": 'first',
                        "borrowed": 'first',
                        "free": 'first',
                        "stepSize": 'first',
                        "minQty": 'first',
                        "minNotional": 'first',
                        "leader_ID": 'unique',
                        "leader_PERFORMANCE": 'mean',
                        "leader_positionAmount": 'sum',
                        "leader_markPrice": 'mean',
                        "TARGET_SHARE": 'sum',
                        }).reset_index()
                    
                    positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["TARGET_SHARE"].abs()
                    positions_opened_changed = positions_opened_changed.sort_values(by=["leader_PERFORMANCE", "TARGET_SHARE"], ascending=False)
                    positions_opened_changed["CUMULATIVE_SHARE"] = positions_opened_changed["TARGET_SHARE"].cumsum()
                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * valueUSDT * user_leverage

                    positions_opened_changed = positions_opened_changed.loc[positions_opened_changed["CUMULATIVE_SHARE"] <=  user["detail"]["data"]["TARGET_RATIO"]]
                    user_invested_ratio = positions_opened_changed["CUMULATIVE_SHARE"].values[-1]

                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * valueUSDT * user_leverage
                    positions_opened_changed.loc[positions_opened_changed["leader_positionAmount"] < 0, "TARGET_VALUE"] *= -1

                    print(positions_opened_changed)
                    
                    # excess_pool = live_pool.copy()[(live_pool["borrowed"] != 0) & (live_pool["borrowed"] > live_pool["netAsset"].abs())]
                    # excess_pool = excess_pool.groupby('symbol').first()
                    # excess_pool["FREE_VALUE"] = excess_pool["free"] * excess_pool["leader_markPrice"]
                    # excess_pool = self.validate_amounts(excess_pool, "free", "FREE_VALUE", "leader_markPrice")
                    # excess_pool = excess_pool.loc[excess_pool["FREE_VALUE"] > 2]

                    if collateral_margin_level > 1.15:
                        positions_opened_changed = positions_opened_changed[positions_opened_changed["leader_symbol"].isin(mix_diff) | positions_opened_changed["symbol"].isna()]
                    
                    positions_opened_changed["TARGET_AMOUNT"] = positions_opened_changed["TARGET_VALUE"] / positions_opened_changed["leader_markPrice"]

                    positions_opened_changed = self.validate_amounts(positions_opened_changed, "TARGET_AMOUNT", "TARGET_VALUE", "leader_markPrice")
                    positions_opened_changed = positions_opened_changed[positions_opened_changed["TARGET_AMOUNT_PASS"]]
                    positions_opened_changed['leader_ID'] = positions_opened_changed['leader_ID'].astype(str)
                
                positions_opened = positions_opened_changed.copy()[positions_opened_changed["symbol"].isna()].set_index("final_symbol")
                    
                positions_changed = positions_opened_changed.copy()[~positions_opened_changed["symbol"].isna()]
                if len(positions_changed) > 0:
                    positions_changed["CURRENT_VALUE"] = positions_changed["netAsset"] * positions_changed["leader_markPrice"]
                    positions_changed["DIFF_AMOUNT"] = positions_changed["TARGET_AMOUNT"] - positions_changed["netAsset"]
                    positions_changed["DIFF_VALUE"] = positions_changed["TARGET_VALUE"] - positions_changed["CURRENT_VALUE"]

                    positions_changed = self.validate_amounts(positions_changed, "netAsset", "CURRENT_VALUE", "leader_markPrice")
                    positions_changed = self.validate_amounts(positions_changed, "DIFF_AMOUNT", "DIFF_VALUE", "leader_markPrice")

                    positions_changed = positions_changed[positions_changed["DIFF_AMOUNT_PASS"]].set_index("final_symbol")

                    positions_changed["DIFF_VALUE_ABS"] = positions_changed["DIFF_VALUE"].abs()
                    positions_changed = positions_changed.sort_values(by=["DIFF_VALUE_ABS"], ascending=False)
                
                    positions_changed["OPEN"] = ((positions_changed["DIFF_AMOUNT"] > 0) & (positions_changed["TARGET_AMOUNT"] > 0)) | ((positions_changed["DIFF_AMOUNT"] < 0) & (positions_changed["TARGET_AMOUNT"] < 0))
                    positions_changed["SWITCH_DIRECTION"] = ((positions_changed["netAsset"] > 0) & (positions_changed["TARGET_AMOUNT"] < 0)) | ((positions_changed["netAsset"] < 0) & (positions_changed["TARGET_AMOUNT"] > 0))


                if any([len(positions_closed) > 0, len(positions_closed) > 0, len(positions_changed) > 0]): #, len(excess_pool) > 0
                    lifecycle["tick_boost"] = True
                    
            else:
                print(f'[{utils.current_readable_time()}]: Updating Positions')

                positions_closed = live_pool.copy()
                positions_closed = await self.get_symbol_prices(bot, positions_closed)
                positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE", "SYMBOL_PRICE")
                positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")
                positions_opened = []
                positions_changed = []
                n_leaders = 0
                active_leaders = []
                # excess_pool = []
                
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
                "positions": user_positions.set_index("asset").to_dict(),
                # "mix": new_user_mix
            }

            return user_account_update, positions_closed, positions_opened, positions_changed#, excess_pool

        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_update', None)


    async def user_account_close(self, bot, user, new_user_mix, dropped_leaders):
        try:
            user_account_update = {
                # "account": {
                    # "levered_ratio": levered_ratio,
                    # "unlevered_ratio": unlevered_ratio,
                # },
                "mix": new_user_mix
            }
                      
            if len(dropped_leaders) > 0:
                user_leaders = user["leaders"]["data"]

                for binance_id in dropped_leaders:
                    user_leaders["WEIGHT"].pop(binance_id)

                user_account_update.update({"leaders": user_leaders})

            return user_account_update
        
        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_close', None)
    

    async def repay_position(self, bot, symbol, amount:float, min_amount:float, stepSize:str):
        # weight = 6
        # try:
        amount = self.truncate_amount(abs(amount), stepSize)
        min_amount = self.truncate_amount(abs(min_amount), stepSize)
        await self.open_position(bot, symbol, min_amount, min_amount, False)
        await self.close_position(bot, symbol, -amount - min_amount, min_amount, False)
        # response = self.client.borrow_repay(asset='USDT', symbol=symbol, amount=, type='REPAY', isIsolated='FALSE')

        # return response

        # except Exception as e:
        #     print(e)

    
    async def open_position(self, bot, symbol:str, amount:float, min_amount:float, retry=True):
        # weight = 6
        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='MARGIN_BUY')

            return response

        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.' and retry:
                await self.close_position(bot, symbol, -min_amount if side == 'BUY' else min_amount, min_amount, False)
                await self.open_position(bot, symbol, amount + min_amount, min_amount, False)
                await self.handle_exception(bot, bot, e, 'close_position - insufficient balance', None, notify=False)

                # response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

                return response
            else:
                print(e)
                

    async def close_position(self, bot, symbol:str, amount:float, min_amount:float, retry=True):
        # weight = 6
        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_REPAY')

            return response
        
        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.' and retry:
                await self.open_position(bot, symbol, min_amount if side == 'SELL' else -min_amount, min_amount, False)
                await self.close_position(bot, symbol, amount + min_amount, min_amount, False)
                await self.handle_exception(bot, bot, e, 'close_position - insufficient balance', None, notify=False)

                # response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')

                # return response
            else:
                print(e)

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


    async def handle_exception(self, bot, user, error, source, symbol, notify=True):
        trace = traceback.format_exc()
        print(trace)
        await self.app.log.create(bot, user, 'ERROR', f'client/{source}', 'TRADE', f'Error in Binance API: {symbol} - {error}', details=trace)

        pass
