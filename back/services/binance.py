import os
from binance.spot import Spot
from urllib.parse import urlencode
import traceback
from lib import utils
import pandas as pd
import numpy as np
import math
from decimal import Decimal, ROUND_DOWN


class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY)

    
    async def get_precision(self, bot, symbol):
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
            await self.handle_exception(bot, bot, e, 'get_precision', symbol)

    async def get_precisions(self, bot, dataframe):
        precisions = pd.DataFrame(columns=["stepSize", "minQty", "minNotional"])

        for symbol in dataframe["final_symbol"].unique():
            symbol, precision = await self.get_precision(bot, symbol)
            precisions.loc[symbol] = precision
        
        dataframe = dataframe.merge(precisions, left_on="final_symbol", right_index=True, how='left')

        return dataframe

    def get_final_symbol(self, symbol):
        if symbol.startswith('1000') and symbol not in ["1000SATSUSDT"]:
            return pd.Series([symbol[4:], True])
        elif symbol in ["LUNA2USDT"]:
            return pd.Series([symbol.replace('2', ''), False])
        else:
            return pd.Series([symbol, False])
    
    async def get_prices(self, bot, dataframe, existing_price_column=None):
        if existing_price_column:
            dataframe["SYMBOL_PRICE"] = dataframe.apply(lambda row: row[existing_price_column] if pd.notna(row[existing_price_column]) else float(self.app.binance.client.ticker_price(row["symbol"])["price"]), axis=1)
        else:
            dataframe["SYMBOL_PRICE"] = dataframe["SYMBOL_PRICE"].apply(lambda symbol: float(self.app.binance.client.ticker_price(symbol)["price"]))

        dataframe["CURRENT_VALUE"] = dataframe["netAsset"] * dataframe["SYMBOL_PRICE"]

        return dataframe

    def handle_positions(self, dataframe):
        dataframe['TOTAL_TARGET_SHARE'] = dataframe.groupby('final_symbol')['TARGET_SHARE'].transform('sum')
        dataframe["POSITION_WEIGHT"] = dataframe["TARGET_SHARE"] / dataframe["TOTAL_TARGET_SHARE"]
        dataframe["WEIGHTED_PERFORMANCE"] = dataframe['leader_PERFORMANCE'] * dataframe["POSITION_WEIGHT"]
        dataframe = dataframe.groupby("final_symbol").agg({
            "symbol": 'first',
            "leader_symbol": 'first',
            "netAsset": 'first',
            "borrowed": 'first',
            "free": 'first',
            "stepSize": 'first',
            "minQty": 'first',
            "minNotional": 'first',
            "leader_ID": 'unique',
            "WEIGHTED_PERFORMANCE": 'sum',
            "leader_positionAmount": 'sum',
            "leader_markPrice": 'mean',
            "TARGET_SHARE": 'sum',
            }).reset_index()
        
        return dataframe

    def truncate_amount(self, amount, stepSize):
        # print(amount, stepSize)
        # decimals = stepSize.split('1')[0].count('0')

        # multiplier = 10 ** decimals if decimals > 0 else 1
        # final_amount = math.floor(abs(amount) * multiplier) / multiplier
        # return final_amount if amount >= 0 else -final_amount

        # final_amount = round(amount, decimals)
        # return final_amount

        amount = Decimal(amount)
        decimals = Decimal(stepSize)
        truncated = (amount // decimals) * decimals
        final_amount = float(truncated.quantize(decimals, rounding=ROUND_DOWN))

        return final_amount

    def validate_amounts(self, dataframe, amount_column, value_column, price_column):
        truncated_amount_column = amount_column + "_TRUNCATED"
        dataframe[truncated_amount_column] = dataframe.apply(lambda row: self.truncate_amount(row[amount_column], row["stepSize"]), axis=1)
        dataframe[amount_column + "_PASS"] = (dataframe[value_column].abs() > dataframe["minNotional"] * 1.05) & (dataframe[truncated_amount_column].abs() > dataframe["minQty"])
        dataframe["MIN_AMOUNT"] = np.maximum(
            dataframe["minNotional"] / dataframe[price_column], 
            dataframe["minQty"] * (dataframe["minNotional"] / dataframe[price_column])
            ) * 1.05
        dataframe["MIN_AMOUNT"] = dataframe.apply(lambda row: self.truncate_amount(row["MIN_AMOUNT"], row["stepSize"]), axis=1)

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
                new_positions[["final_symbol", "thousand"]] = new_positions["symbol"].apply(lambda symbol: self.get_final_symbol(symbol))
                new_positions.loc[new_positions["thousand"], "markPrice"] /= 1000

                live_pool = live_pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_final_symbol", how='outer')
                live_pool["final_symbol"] = live_pool.apply(lambda row: pd.Series(row["leader_final_symbol"] if isinstance(row["leader_final_symbol"], str) else row["symbol"]), axis=1)
                live_pool = live_pool.merge(user_leaders.add_prefix("user_"), left_on="leader_ID", right_index=True, how='left')
                live_pool = await self.get_precisions(bot, live_pool)
                # live_pool[["netAsset", "borrowed", "free"]] = live_pool[["netAsset", "borrowed", "free"]].fillna(0)
                active_leaders = live_pool["leader_ID"].dropna().unique()
                n_leaders = active_leaders.size

                print(f'[{utils.current_readable_time()}]: Updating Positions for {n_leaders} leaders')

                positions_opened_changed = live_pool.copy()[~live_pool["leader_symbol"].isna()]
                if len(positions_opened_changed) > 0:
                    user_leverage = user["account"]["data"]["leverage"] - 1
                    positions_closed, positions_excess = [], []

                    positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["leader_POSITION_SHARE"] * positions_opened_changed["leader_INVESTED_RATIO"] * positions_opened_changed["leader_AVERAGE_LEVERAGE"] * positions_opened_changed["user_WEIGHT"] * (1 / len(user["leaders"]["data"]["WEIGHT"])) * user["detail"]["data"]["TARGET_RATIO"]

                    # print(positions_opened_changed)
                    positions_short = positions_opened_changed.copy().loc[positions_opened_changed["leader_positionAmount"] < 0]
                    # print(positions_short)
                    positions_short = self.handle_positions(positions_short)
                    # print(positions_short)
                    positions_long = positions_opened_changed.copy().loc[positions_opened_changed["leader_positionAmount"] > 0]
                    positions_long = self.handle_positions(positions_long)
                    # print(positions_long)

                    positions_opened_changed = pd.concat([positions_short, positions_long])
                    positions_opened_changed = positions_opened_changed.sort_values(by=['final_symbol', 'TARGET_SHARE'], ascending=[True, False])
                    positions_opened_changed = positions_opened_changed.drop_duplicates(subset='final_symbol', keep='first')

                    # positions_opened_changed.loc[positions_opened_changed["leader_positionAmount"] < 0, "TARGET_SHARE"] *= -1

                    # positions_opened_changed = positions_opened_changed.groupby("final_symbol").agg({
                    #     "symbol": 'first',
                    #     "leader_symbol": 'first',
                    #     "netAsset": 'first',
                    #     "borrowed": 'first',
                    #     "free": 'first',
                    #     "stepSize": 'first',
                    #     "minQty": 'first',
                    #     "minNotional": 'first',
                    #     "leader_ID": 'unique',
                    #     "leader_PERFORMANCE": 'mean',
                    #     "leader_positionAmount": 'sum',
                    #     "leader_markPrice": 'mean',
                    #     "TARGET_SHARE": 'mean',
                    #     }).reset_index()

                    # positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["TARGET_SHARE"].abs()
                    positions_opened_changed = positions_opened_changed.sort_values(by=["WEIGHTED_PERFORMANCE", "TARGET_SHARE"], ascending=False)
                    positions_opened_changed["CUMULATIVE_SHARE"] = positions_opened_changed["TARGET_SHARE"].cumsum()
                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * valueUSDT * user_leverage

                    last_position = positions_opened_changed[positions_opened_changed['CUMULATIVE_SHARE'] > user["detail"]["data"]["TARGET_RATIO"]].iloc[0] if not positions_opened_changed[positions_opened_changed['CUMULATIVE_SHARE'] > user["detail"]["data"]["TARGET_RATIO"]].empty else pd.Series([])

                    positions_opened_changed = positions_opened_changed.loc[positions_opened_changed["CUMULATIVE_SHARE"] <=  user["detail"]["data"]["TARGET_RATIO"]]

                    truncated_invested_ratio = positions_opened_changed["CUMULATIVE_SHARE"].values[-1]

                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * valueUSDT * user_leverage
                    positions_opened_changed.loc[positions_opened_changed["leader_positionAmount"] < 0, "TARGET_VALUE"] *= -1

                    last_symbol = last_position["symbol"] if not last_position.empty else ''
                    # print(last_symbol)

                    positions_closed_excess = live_pool.copy().dropna(subset='symbol')
                    positions_closed_excess = positions_closed_excess.loc[(~live_pool["symbol"].isin(positions_opened_changed["final_symbol"])) | (live_pool["borrowed"] != 0) & (live_pool["borrowed"] > live_pool["netAsset"].abs())]
                    # print(positions_closed_excess)
                    if len(positions_closed_excess) > 0:
                        positions_closed_excess = positions_closed_excess.groupby('symbol').agg({
                            "netAsset": 'first',
                            "borrowed": 'first',
                            "free": 'first',
                            "stepSize": 'first',
                            "minQty": 'first',
                            "minNotional": 'first',
                        }).reset_index()

                        positions_closed_excess = positions_closed_excess.merge(positions_opened_changed[['final_symbol', 'leader_markPrice']], left_on='symbol', right_on='final_symbol', how='left')
                        positions_closed_excess = await self.get_prices(bot, positions_closed_excess, 'leader_markPrice')
            
                        positions_closed = positions_closed_excess.copy()[(~positions_closed_excess["symbol"].isin(positions_opened_changed["final_symbol"])) & (positions_closed_excess["symbol"] != last_symbol)]
                        if len(positions_closed) > 0:
                            # print(positions_closed)
                            positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE", "SYMBOL_PRICE")
                            positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")

                        positions_excess = positions_closed_excess.copy()[(positions_closed_excess["borrowed"] != 0) & (positions_closed_excess["borrowed"] > positions_closed_excess["netAsset"].abs())]
                        if len(positions_excess) > 0:
                            # print('positions_excess')
                            # print(positions_excess)
                            positions_excess["FREE_VALUE"] = positions_excess["free"] * positions_excess["SYMBOL_PRICE"]
                            positions_excess = self.validate_amounts(positions_excess, "free", "FREE_VALUE", "SYMBOL_PRICE")
                            positions_excess = positions_excess.loc[positions_excess["FREE_VALUE"] > 2].set_index("symbol")

                    print(positions_opened_changed)

                    if collateral_margin_level > 1.15:
                        positions_opened_changed = positions_opened_changed[positions_opened_changed["leader_symbol"].isin(mix_diff) | positions_opened_changed["symbol"].isna()]

                    if not last_position.empty:
                        last_diff_pass = False
                        last_position["TARGET_SHARE"] = user["detail"]["data"]["TARGET_RATIO"] - truncated_invested_ratio
                        last_position["TARGET_VALUE"] = last_position["TARGET_SHARE"] * valueUSDT * user_leverage
                        last_position["TARGET_VALUE"] = last_position["TARGET_VALUE"] * -1 if last_position["leader_positionAmount"] < 0 else last_position["TARGET_VALUE"]
                        last_diff_pass = abs(last_position["TARGET_VALUE"] / last_position["leader_markPrice"] - last_position["netAsset"]) / abs(last_position["netAsset"]) > 0.1 if last_position["netAsset"] else True

                        if (len(positions_opened_changed) > 0 or last_position["symbol"] in mix_diff) and last_diff_pass:
                            last_position["CUMULATIVE_SHARE"] = user["detail"]["data"]["TARGET_RATIO"]
                            positions_opened_changed.loc[len(positions_opened_changed)] = last_position
                            # print(last_position)

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

                if any([len(positions_opened) > 0, len(positions_closed) > 0, len(positions_changed) > 0, len(positions_excess) > 0]):
                    lifecycle["tick_boost"] = True
                    
            else:
                print(f'[{utils.current_readable_time()}]: Updating Positions')

                positions_closed = live_pool.copy()
                positions_closed = await self.get_prices(bot, positions_closed)
                positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE", "SYMBOL_PRICE")
                positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")

                positions_excess = positions_closed.copy()[(positions_closed["borrowed"] != 0) & (positions_closed["borrowed"] > positions_closed["netAsset"].abs())]
                positions_excess["FREE_VALUE"] = positions_excess["free"] * positions_excess["SYMBOL_PRICE"]
                positions_excess = self.validate_amounts(positions_excess, "free", "FREE_VALUE", "SYMBOL_PRICE")
                positions_excess = positions_excess.loc[positions_excess["FREE_VALUE"] > 2]

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
                "positions": user_positions.set_index("asset").to_dict(),
                # "mix": new_user_mix
            }

            return user_account_update, positions_closed, positions_opened, positions_changed, positions_excess

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
    

    async def repay_position(self, bot, symbol, amount:float, min_amount:float, stepSize:str, new_user_mix):
        # weight = 6
        try:
            response = self.client.borrow_repay(asset='USDT', symbol=symbol, amount=amount, type='REPAY', isIsolated='FALSE')

            return response
        except Exception as e:
            await self.handle_exception(bot, bot, e, 'repay_position', symbol, new_user_mix, notify=False)
            
            amount = self.truncate_amount(abs(amount), stepSize)
            min_amount = self.truncate_amount(abs(min_amount), stepSize)
            await self.open_position(bot, symbol, min_amount, min_amount, new_user_mix, False)
            await self.close_position(bot, symbol, -amount - min_amount, min_amount, new_user_mix, False)

    
    async def open_position(self, bot, symbol:str, amount:float, min_amount:float, new_user_mix, retry=True):
        # weight = 6
        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='MARGIN_BUY')

            return response

        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.':
                await self.handle_exception(bot, bot, '', 'close_position - insufficient balance', None, new_user_mix, notify=False)

                if retry:
                #     await self.close_position(bot, symbol, -min_amount if side == 'BUY' else min_amount, min_amount, new_user_mix, False)
                #     await self.open_position(bot, symbol, amount + min_amount if side == 'BUY' else amount - min_amount, min_amount, new_user_mix, False)
                # else:
                    self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')
            else:
                await self.handle_exception(bot, bot, e, 'close_position - insufficient balance', None, new_user_mix, notify=True)

                

    async def close_position(self, bot, symbol:str, amount:float, min_amount:float, new_user_mix, retry=True):
        # weight = 6
        try:
            side = 'BUY'
            if amount < 0:
                side = 'SELL'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_REPAY')

            return response
        
        except Exception as e:
            if e.args[2] == 'Account has insufficient balance for requested action.':
                await self.handle_exception(bot, bot, '', 'close_position - insufficient balance', symbol, new_user_mix, notify=False)

                if retry:
                #     await self.open_position(bot, symbol, -min_amount if side == 'BUY' else min_amount, min_amount, new_user_mix, False)
                #     await self.close_position(bot, symbol, amount + min_amount if side == 'BUY' else amount - min_amount, min_amount, new_user_mix, False)
                # else:
                    self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType='AUTO_BORROW_REPAY')
            else:
                await self.handle_exception(bot, bot, e, 'close_position - insufficient balance', symbol, new_user_mix, notify=True)



    async def handle_exception(self, bot, user, error, source, symbol, new_user_mix=None, notify=True):
        trace = traceback.format_exc()
        # print(trace)
        if new_user_mix and symbol in new_user_mix.keys():
            new_user_mix["BAG"].pop(symbol)

        await self.app.log.create(bot, user, 'ERROR', f'client/{source}', 'TRADE', f'Error in Binance API: {symbol} - {error}', details=trace)
        pass
